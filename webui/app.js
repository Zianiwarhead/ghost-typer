// Ghost Typer — desktop UI logic.
// Talks to Python only through window.pywebview.api (see webapp.py).

const FEELS = [
  { key: "sluggish",  name: "Sluggish",  wpm: 25,  desc: "Slow, lots of thinking" },
  { key: "casual",    name: "Casual",    wpm: 45,  desc: "Relaxed, everyday" },
  { key: "normal",    name: "Normal",    wpm: 65,  desc: "Typical office worker" },
  { key: "fast",      name: "Fast",      wpm: 105, desc: "Practiced typist" },
  { key: "typewriter",name: "Typewriter",wpm: 80,  desc: "Steady, mechanical" },
];

const el = (id) => document.getElementById(id);

const textInput      = el("textInput");
const textStats      = el("textStats");
const feelSelect      = el("feelSelect");
const wpmSlider       = el("wpmSlider");
const wpmValue        = el("wpmValue");
const countdownInput  = el("countdownInput");
const countdownLabel  = el("countdownLabel");
const startBtn        = el("startBtn");
const pauseBtn        = el("pauseBtn");
const stopBtn         = el("stopBtn");
const progressFill    = el("progressFill");
const statusLine      = el("statusLine");
const typedPreview    = el("typedPreview");
const advancedToggle  = el("advancedToggle");
const advancedPanel   = el("advancedPanel");
const chatModeToggle  = el("chatModeToggle");
const focusLockToggle = el("focusLockToggle");
const doctorBtn       = el("doctorBtn");
const doctorOutput    = el("doctorOutput");
const pasteBtn        = el("pasteBtn");
const loadFileBtn     = el("loadFileBtn");
const clearBtn        = el("clearBtn");

let selectedFeel = "normal";
let pollTimer = null;
let hasResumeAvailable = false;

// ---------------- feel selector ---------------- //

function renderFeels() {
  feelSelect.innerHTML = "";
  FEELS.forEach((f) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "feel-option";
    btn.setAttribute("role", "radio");
    btn.setAttribute("aria-checked", f.key === selectedFeel ? "true" : "false");
    btn.innerHTML = `<span class="feel-name">${f.name}</span><span class="feel-wpm">${f.desc}</span>`;
    btn.addEventListener("click", () => selectFeel(f.key));
    feelSelect.appendChild(btn);
  });
}

function selectFeel(key) {
  selectedFeel = key;
  const feel = FEELS.find((f) => f.key === key);
  if (feel) {
    wpmSlider.value = feel.wpm;
    wpmValue.textContent = `${feel.wpm} wpm`;
  }
  [...feelSelect.children].forEach((btn, i) => {
    btn.setAttribute("aria-checked", FEELS[i].key === key ? "true" : "false");
  });
}

wpmSlider.addEventListener("input", () => {
  wpmValue.textContent = `${wpmSlider.value} wpm`;
  // Manual slider movement de-selects the preset visually if it no longer matches.
  const match = FEELS.find((f) => String(f.wpm) === wpmSlider.value);
  [...feelSelect.children].forEach((btn, i) => {
    btn.setAttribute("aria-checked", match && FEELS[i].key === match.key ? "true" : "false");
  });
});

// ---------------- text well ---------------- //

function updateStats() {
  const n = textInput.value.length;
  if (n === 0) {
    textStats.textContent = "0 characters";
    return;
  }
  const words = textInput.value.trim().split(/\s+/).length;
  const wpm = parseInt(wpmSlider.value, 10) || 65;
  const secs = Math.max(1, Math.round(((n / 5) / wpm) * 60));
  const eta = secs < 60 ? `~${secs}s` : `~${Math.floor(secs / 60)}m ${secs % 60}s`;
  textStats.textContent =
    `${n.toLocaleString()} characters · ${words.toLocaleString()} words · ${eta} at ${wpm} wpm`;
}
textInput.addEventListener("input", updateStats);
wpmSlider.addEventListener("input", updateStats);

pasteBtn.addEventListener("click", async () => {
  try {
    const text = await window.pywebview.api.paste_clipboard();
    if (text) {
      textInput.value = text;
      updateStats();
    }
  } catch (e) {
    statusLine.textContent = "Couldn't read the clipboard.";
  }
});

loadFileBtn.addEventListener("click", async () => {
  try {
    const text = await window.pywebview.api.load_file();
    if (text !== null && text !== undefined) {
      textInput.value = text;
      updateStats();
    }
  } catch (e) {
    statusLine.textContent = "Couldn't load that file.";
  }
});

clearBtn.addEventListener("click", () => {
  textInput.value = "";
  updateStats();
});

// ---------------- countdown display ---------------- //

countdownInput.addEventListener("input", () => {
  countdownLabel.textContent = `${countdownInput.value}s`;
});

// ---------------- advanced drawer ---------------- //

advancedToggle.addEventListener("click", () => {
  const open = advancedPanel.getAttribute("data-open") === "true";
  advancedPanel.hidden = false;
  advancedPanel.setAttribute("data-open", String(!open));
  advancedToggle.setAttribute("aria-expanded", String(!open));
});

doctorBtn.addEventListener("click", async () => {
  doctorOutput.hidden = false;
  doctorOutput.textContent = "Checking…";
  try {
    const report = await window.pywebview.api.run_doctor();
    doctorOutput.textContent = report;
  } catch (e) {
    doctorOutput.textContent = "Couldn't run the check.";
  }
});

// ---------------- start / pause / stop ---------------- //

startBtn.addEventListener("click", async () => {
  const text = textInput.value;
  if (!text.trim() && !hasResumeAvailable) {
    statusLine.textContent = "Paste or type some text first.";
    return;
  }

  const payload = {
    text,
    profile: selectedFeel,
    wpm: parseInt(wpmSlider.value, 10),
    countdown: parseInt(countdownInput.value, 10) || 5,
    chat_mode: chatModeToggle.checked,
    focus_lock: focusLockToggle.checked,
    resume: hasResumeAvailable,
  };

  setRunningUI(true);
  try {
    await window.pywebview.api.start(payload);
  } catch (e) {
    statusLine.textContent = "Couldn't start. Check the Advanced panel's system check.";
    setRunningUI(false);
    return;
  }
  startPolling();
});

pauseBtn.addEventListener("click", async () => {
  try {
    const paused = await window.pywebview.api.pause();
    pauseBtn.textContent = paused ? "Resume" : "Pause";
    pauseBtn.classList.toggle("is-paused", paused);
  } catch (e) { /* no-op */ }
});

stopBtn.addEventListener("click", async () => {
  try {
    await window.pywebview.api.stop();
  } catch (e) { /* no-op */ }
});

function setRunningUI(running) {
  startBtn.disabled = running;
  startBtn.classList.toggle("is-running", running);
  pauseBtn.disabled = !running;
  stopBtn.disabled = !running;
  textInput.disabled = running;
  feelSelect.querySelectorAll("button").forEach((b) => (b.disabled = running));
  wpmSlider.disabled = running;
  if (!running) {
    typedPreview.hidden = true;
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(pollStatus, 200);
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

async function pollStatus() {
  let s;
  try {
    s = await window.pywebview.api.get_status();
  } catch (e) {
    return;
  }
  if (!s) return;

  const pct = s.total > 0 ? Math.min(100, (s.index / s.total) * 100) : 0;
  progressFill.style.width = `${pct}%`;

  if (s.typing) {
    statusLine.textContent = s.message || `Typing… ${s.index}/${s.total} characters`;
    renderTypedPreview(s.index || 0);
  } else {
    stopPolling();
    setRunningUI(false);
    pauseBtn.textContent = "Pause";
    pauseBtn.classList.remove("is-paused");
    hasResumeAvailable = !!s.has_resume;
    startBtn.querySelector(".start-btn-label").textContent = hasResumeAvailable ? "Resume" : "Start";
    statusLine.textContent = s.message || (hasResumeAvailable ? "Stopped — press Resume to continue." : "Done.");
  }
}

// Live "what's been typed" preview: done text dimmed, brass caret, what's next.
function renderTypedPreview(index) {
  const full = textInput.value;
  if (!full) {
    typedPreview.hidden = true;
    return;
  }
  const done = full.slice(0, index);
  const next = full.slice(index, index + 60).split("\n")[0];
  typedPreview.textContent = "";
  const doneSpan = document.createElement("span");
  doneSpan.className = "done-part";
  doneSpan.textContent = done.length > 80 ? "…" + done.slice(-80) : done;
  const caretSpan = document.createElement("span");
  caretSpan.className = "caret-part";
  caretSpan.textContent = next || "✓";
  typedPreview.append(doneSpan, caretSpan);
  typedPreview.hidden = false;
}

// ---------------- init ---------------- //

renderFeels();
selectFeel("normal");
updateStats();
