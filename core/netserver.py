"""
netserver.py — stdlib-only remote control for GhostTyper (no Flask/FastAPI).

Routes:
  GET  /                mobile dashboard (static HTML below)
  GET  /api/v1/status   {ok, typing} — needs the token, like everything else
  POST /api/v1/type     {target, text, mode, theme, profile, typos, countdown}

Security posture (deliberate, documented):
  - Bearer token REQUIRED on every API call (constant-time compare).
  - Binds 127.0.0.1 unless --serve-lan explicitly opts into LAN exposure.
  - No encryption claims: on a trusted LAN the token is the protection.
    Anything beyond (TLS, public internet) is out of scope — say so loudly.
"""

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

MAX_BYTES = 2 * 1024 * 1024

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GhostTyper Remote</title>
<style>
body{font-family:'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;margin:0;padding:20px}
.container{max-width:520px;margin:auto;background:#161b22;padding:20px;border-radius:8px;border:1px solid #30363d}
h2{color:#58a6ff;border-bottom:1px solid #30363d;padding-bottom:8px;margin-top:0}
label{display:block;margin:12px 0 4px;font-weight:bold;font-size:14px}
input,textarea,select{width:100%;padding:10px;background:#0d1117;border:1px solid #30363d;color:#fff;border-radius:6px;box-sizing:border-box}
textarea{height:110px;resize:vertical}
button{width:100%;margin-top:18px;padding:12px;background:#238636;border:0;color:#fff;font-weight:bold;border-radius:6px;cursor:pointer;font-size:16px}
button:hover{background:#2ea043}
#status{margin-top:15px;padding:10px;border-radius:6px;display:none;font-size:14px}
.ok{background:rgba(35,134,54,.15);color:#56d364;border:1px solid #238636}
.err{background:rgba(248,81,73,.15);color:#ffa198;border:1px solid #f85149}
.row{display:flex;gap:10px}.row>div{flex:1}
</style>
</head>
<body>
<div class="container">
<h2>GhostTyper Remote</h2>
<label>API token (printed in the host terminal)</label>
<input type="password" id="token" autocomplete="off">
<label>Target window (title keyword or PID)</label>
<input type="text" id="target" placeholder="e.g. Untitled - Notepad">
<div class="row"><div>
<label>Mode</label>
<select id="mode"><option value="human">Background type</option><option value="rich">Formatted paste</option><option value="table">Table paste</option></select>
</div><div>
<label>Theme (rich/table)</label>
<select id="theme"><option value="steel">Steel</option><option value="matrix">Matrix</option><option value="dracula">Dracula</option></select>
</div></div>
<div class="row"><div>
<label>Profile (human)</label>
<input type="text" id="profile" value="normal">
</div><div>
<label>&nbsp;</label>
<div><input type="checkbox" id="typos" style="width:auto"> human typos</div>
</div></div>
<label>Text (rich: **bold**/# heads · table: Title | h1,h2 | r1,r2)</label>
<textarea id="text"></textarea>
<button onclick="send()">Dispatch</button>
<div id="status"></div>
</div>
<script>
async function send(){
  const st=document.getElementById('status');
  const body={target:document.getElementById('target').value,
    text:document.getElementById('text').value,
    mode:document.getElementById('mode').value,
    theme:document.getElementById('theme').value,
    profile:document.getElementById('profile').value,
    typos:document.getElementById('typos').checked};
  try{
    const r=await fetch('/api/v1/type',{method:'POST',
      headers:{'Content-Type':'application/json',
        'Authorization':'Bearer '+document.getElementById('token').value},
      body:JSON.stringify(body)});
    const d=await r.json();
    st.style.display='block'; st.className=r.ok?'ok':'err';
    st.innerText=(r.ok?'OK: ':'Error '+(d.status||r.status)+': ')+(d.message||JSON.stringify(d));
  }catch(e){ st.style.display='block'; st.className='err'; st.innerText='Network error: '+e; }
}
</script>
</body>
</html>"""


class _ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class GhostAPIHandler(BaseHTTPRequestHandler):
    token: str = ""
    dispatch_fn = None   # (payload: dict) -> (code: int, message: str)
    status_fn = None     # () -> bool (typing?)

    def log_message(self, *args):
        return

    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self) -> bool:
        want = "Bearer " + (self.token or "")
        got = self.headers.get("Authorization", "")
        return bool(self.token) and hmac.compare_digest(want, got)

    def do_GET(self):
        if self.path == "/":
            body = DASHBOARD_HTML.encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/v1/status":
            if not self._authed():
                self._send(401, {"status": "error", "message": "bad or missing token"})
                return
            typing = bool(self.status_fn and self.status_fn())
            self._send(200, {"status": "ok", "typing": typing})
            return
        self._send(404, {"status": "error", "message": "unknown endpoint"})

    def do_POST(self):
        if self.path != "/api/v1/type":
            self._send(404, {"status": "error", "message": "unknown endpoint"})
            return
        if not self._authed():
            self._send(401, {"status": "error", "message": "bad or missing token"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except (TypeError, ValueError):
            self._send(400, {"status": "error", "message": "Content-Length required"})
            return
        if length > MAX_BYTES:
            self._send(413, {"status": "error", "message": "payload too large"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
        except Exception:
            self._send(400, {"status": "error", "message": "malformed JSON"})
            return
        if not isinstance(payload, dict) or not payload.get("text") or not payload.get("target"):
            self._send(400, {"status": "error", "message": "need 'text' and 'target'"})
            return
        try:
            code, message = self.dispatch_fn(payload)
        except Exception as e:
            self._send(500, {"status": "error", "message": f"dispatch failed: {e}"})
            return
        if code == 200:
            self._send(200, {"status": "dispatched", "message": message})
        elif code == 409:
            self._send(409, {"status": "error", "message": message})
        else:
            self._send(400, {"status": "error", "message": message})


def start_in_thread(host: str, port: int, token: str, dispatch_fn, status_fn):
    """Starts the server on a daemon thread. Returns (server, thread)."""
    # staticmethod: plain functions stored on the class would otherwise
    # become bound methods (self injected) when accessed via the instance.
    GhostAPIHandler.token = token
    GhostAPIHandler.dispatch_fn = staticmethod(dispatch_fn)
    GhostAPIHandler.status_fn = staticmethod(status_fn)
    server = _ThreadedServer((host, port), GhostAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True,
                              kwargs={"poll_interval": 0.2})
    thread.start()
    return server, thread
