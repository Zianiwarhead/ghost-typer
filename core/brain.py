"""
brain.py — pluggable model backend for screen Q&A.

Two backends, one ask():
  api    OpenAI-compatible chat endpoint over urllib (no SDK). Handles text
         and vision (screenshot as data-URL). Default; genuinely capable.
  local  Tiny ONNX model on CPU (SmolLM2-360M, ~200MB q4). Fully offline,
         much weaker, slow-ish. EXPERIMENTAL — setup via download_model().

No key, no model files, no network: every path fails with a message that
says exactly how to fix it.
"""

import base64
import json
import os
import urllib.error
import urllib.request

SYSTEM_PROMPT = (
    "You are the brain of GhostTyper, a tool that types into desktop apps "
    "for the user. You see a UI element tree (and maybe a screenshot) of "
    "the current screen. Answer the user's question concisely and "
    "concretely: name exact buttons, fields, and values you can see. "
    "If asked to choose among options, reply with the EXACT visible label "
    "of your choice on its own first line, then one line of reasoning. "
    "If the screen doesn't contain what was asked about, say so plainly "
    "instead of guessing.")

LOCAL_MODEL_ID = "onnx-community/SmolLM2-360M-Instruct"
LOCAL_FILES = ("onnx/model_q4.onnx", "tokenizer.json")


def model_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".ghost-typer", "models", "smolm2")


def _api_ask(api_url: str, api_key: str, model: str, question: str,
             context: str, shot_jpeg, timeout: int, max_tokens: int) -> str:
    if not api_key:
        raise RuntimeError("API brain needs a key: --brain-key or GHOST_BRAIN_KEY env "
                           "(OpenAI, OpenRouter, or any OpenAI-compatible endpoint).")
    user_block = [{"type": "text", "text": f"Screen context:\n{context}\n\nQuestion: {question}"}]
    if shot_jpeg:
        b64 = base64.b64encode(shot_jpeg).decode('ascii')
        user_block.append({"type": "image_url",
                           "image_url": {"url": "data:image/jpeg;base64," + b64}})
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": user_block}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }).encode('utf-8')
    req = urllib.request.Request(
        api_url.rstrip('/') + '/chat/completions', data=body,
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {api_key}'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')[:300]
        raise RuntimeError(f"brain endpoint HTTP {e.code}: {detail}")
    except Exception as e:
        raise RuntimeError(f"brain endpoint unreachable ({api_url}): {e}")
    try:
        content = data['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"brain endpoint gave no usable answer: {str(data)[:300]}")
    if isinstance(content, list):  # some endpoints return part lists
        content = ''.join(p.get('text', '') for p in content if isinstance(p, dict))
    return (content or '').strip()


def local_ready() -> tuple:
    """(ready: bool, reason). Checks onnxruntime + model files."""
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        return False, "pip install onnxruntime tokenizers"
    missing = [f for f in LOCAL_FILES
               if not os.path.exists(os.path.join(model_dir(), os.path.basename(f)))]
    if missing:
        return False, (f"model files missing ({', '.join(missing)}). "
                       f"Run: python main.py --brain-download (~200MB from HuggingFace).")
    try:
        import tokenizers  # noqa: F401
    except Exception:
        return False, "pip install tokenizers"
    return True, ""


def download_model() -> str:
    """Fetches the tiny model over plain HTTPS into ~/.ghost-typer/models/smolm2/."""
    base = f"https://huggingface.co/{LOCAL_MODEL_ID}/resolve/main/"
    dest = model_dir()
    os.makedirs(dest, exist_ok=True)
    for remote in LOCAL_FILES:
        url = base + remote
        out = os.path.join(dest, os.path.basename(remote))
        if os.path.exists(out):
            print(f"  have {os.path.basename(remote)}")
            continue
        print(f"  downloading {remote} ...")
        urllib.request.urlretrieve(url, out)
        print(f"  saved {out}")
    return dest


def _local_ask(question: str, context: str, max_tokens: int) -> str:
    import numpy as np
    ready, reason = local_ready()
    if not ready:
        raise RuntimeError(f"local brain not set up: {reason}")
    import onnxruntime as ort
    from tokenizers import Tokenizer
    dest = model_dir()
    sess = ort.InferenceSession(os.path.join(dest, "model_q4.onnx"),
                                providers=['CPUExecutionProvider'])
    tok = Tokenizer.from_file(os.path.join(dest, "tokenizer.json"))
    eos = tok.token_to_id("<|im_end|>")

    def enc(s: str):
        return tok.encode(s).ids

    prompt_ids = enc(
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\nScreen context:\n{context}\n\nQuestion: {question}<|im_end|>\n"
        f"<|im_start|>assistant\n")
    ids = list(prompt_ids)
    for _ in range(max(1, max_tokens)):
        logits = sess.run(None, {'input_ids': np.array([ids], dtype=np.int64)})[0]
        nxt = int(np.argmax(logits[0, -1]))
        if eos is not None and nxt == eos:
            break
        ids.append(nxt)
    return tok.decode(ids[len(prompt_ids):]).strip()


def ask(question: str, context: str = "", shot_jpeg=None, backend: str = 'api',
        model: str | None = None, api_url: str = 'https://api.openai.com/v1',
        api_key: str | None = None, timeout: int = 60,
        max_tokens: int = 300) -> str:
    """Ask the brain. Returns the answer text (raises RuntimeError if unset)."""
    if backend == 'local':
        return _local_ask(question, context, max_tokens)
    if backend != 'api':
        raise ValueError(f"unknown brain backend {backend!r} (api|local)")
    key = api_key or os.environ.get('GHOST_BRAIN_KEY') or os.environ.get('OPENAI_API_KEY')
    return _api_ask(api_url, key or "", model or 'gpt-4o-mini', question,
                    context, shot_jpeg, timeout, max_tokens)


def capture_screen(max_width: int = 1280):
    """Screenshot as (jpeg_bytes | None, note). Pillow-based, guarded."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
    except Exception as e:
        return None, f"screenshot unavailable: {e}"
    try:
        import io
        if img.width > max_width:
            img = img.resize((max_width, int(img.height * max_width / img.width)))
        buf = io.BytesIO()
        img.convert('RGB').save(buf, format='JPEG', quality=60)
        return buf.getvalue(), ""
    except Exception as e:
        return None, f"screenshot encode failed: {e}"


def build_context(max_nodes: int = 150, screenshot: bool = False):
    """(tree_text, jpeg_bytes|None, notes). Never raises."""
    notes = []
    try:
        from core import uia
        if not uia.available():
            return "", None, ["UI Automation unavailable (Windows + uiautomation package)."]
        tree = uia.dump_tree(depth=3, max_nodes=max_nodes)
        text = uia.tree_to_text(tree)
    except Exception as e:
        return "", None, [f"screen read failed: {e}"]
    shot = None
    if screenshot:
        shot, note = capture_screen()
        if note:
            notes.append(note)
    if not text.strip():
        notes.append("screen tree came back empty.")
    return text, shot, notes
