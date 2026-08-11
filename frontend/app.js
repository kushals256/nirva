const API = (window.NIRVA_CONFIG && window.NIRVA_CONFIG.API_BASE) || window.location.origin;
const WS_URL = `${API.replace(/^http/, "ws")}/ws/voice`;

let sessionId = null;
let docId = null;
let ws = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let currentAudio = null;
let hasMessages = false;

const $ = (id) => document.getElementById(id);

function setStatus(text, active = false) {
  const pill = $("statusPill");
  pill.textContent = text;
  pill.classList.toggle("active", active);
}

function setConn(online) {
  $("connDot").className = `status-dot ${online ? "online" : "offline"}`;
}

function stopAudio() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
  window.speechSynthesis.cancel();
}

function playAudioBase64(b64, format = "mp3") {
  stopAudio();
  const mime = format === "mp3" ? "audio/mpeg" : `audio/${format}`;
  currentAudio = new Audio(`data:${mime};base64,${b64}`);
  currentAudio.onended = () => {
    currentAudio = null;
    setStatus("Ready — hold mic to talk");
  };
  currentAudio.onerror = () => {
    setStatus("Audio playback failed");
    currentAudio = null;
  };
  currentAudio.play().catch(() => setStatus("Click mic to allow audio"));
}

function speakBrowserFallback(text) {
  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  const voices = window.speechSynthesis.getVoices();
  const ranked = [
    (v) => v.lang === "en-IN" && /neerja|prabhat|rishi|veena/i.test(v.name),
    (v) => v.lang === "en-IN",
    (v) => v.lang === "hi-IN",
    (v) => /rishi|veena|neerja|prabhat/i.test(v.name),
    (v) => v.lang.startsWith("en-IN"),
    (v) => v.lang.startsWith("en"),
  ];
  for (const pick of ranked) {
    const voice = voices.find(pick);
    if (voice) { utter.voice = voice; break; }
  }
  utter.rate = 0.95;
  window.speechSynthesis.speak(utter);
}

function hideEmptyState() {
  if (!hasMessages) {
    hasMessages = true;
    const empty = $("emptyState");
    if (empty) empty.remove();
  }
}

function appendTranscript(role, text) {
  hideEmptyState();
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.innerHTML = `<div class="label">${role === "user" ? "You" : "Tutor"}</div>${escapeHtml(text)}`;
  $("transcript").appendChild(div);
  $("transcript").scrollTop = $("transcript").scrollHeight;
}

function formatDetail(text) {
  return text
    .split("\n")
    .map((line) => {
      if (!line.trim()) return "<br />";
      if (line.startsWith("📄")) return `<p class="answer-head">${escapeHtml(line)}</p>`;
      if (line.startsWith("Kahan:") || line.startsWith("Where:")) {
        return `<p class="answer-where">${escapeHtml(line).replace(/`([^`]+)`/g, "<code>$1</code>")}</p>`;
      }
      if (line.startsWith("Kya ") || line.startsWith("What ") || line.startsWith("Code ") || line.startsWith("Aur ") || line.startsWith("Related ")) {
        return `<p class="answer-meta">${escapeHtml(line)}</p>`;
      }
      return `<p>${escapeHtml(line)}</p>`;
    })
    .join("");
}

function showReply(data) {
  const detail = data.answer_detail || data.text || "";
  const replyEl = $("reply");
  replyEl.innerHTML = detail
    ? formatDetail(detail)
    : '<p class="muted">No answer yet.</p>';
  sessionId = data.session_id || sessionId;

  const citesEl = $("citations");
  citesEl.innerHTML = "";
  const hasCites = (data.citations || []).length > 0;
  if (!hasCites) {
    citesEl.innerHTML = '<p class="muted">No citations for this answer.</p>';
  } else {
    data.citations.forEach((c) => {
      const el = document.createElement("div");
      el.className = "cite";
      el.innerHTML = `<div class="page-badge">Page ${c.page}</div><div>${escapeHtml(c.text.slice(0, 220))}${c.text.length > 220 ? "…" : ""}</div>`;
      citesEl.appendChild(el);
    });
  }

  const toolsEl = $("tools");
  toolsEl.innerHTML = "";
  const hasTools = (data.tool_calls || []).length > 0;
  if (!hasTools) {
    toolsEl.innerHTML = '<p class="muted">No tools used.</p>';
  } else {
    data.tool_calls.forEach((t) => {
      const el = document.createElement("div");
      el.className = "tool";
      const args = escapeHtml(JSON.stringify(t.arguments, null, 0));
      const preview = t.result
        ? `<div class="tool-result">${escapeHtml(String(t.result).slice(0, 300))}${String(t.result).length > 300 ? "…" : ""}</div>`
        : "";
      el.innerHTML = `<div class="tool-name">${escapeHtml(t.name)}</div><div class="tool-args">${args}</div>${preview}`;
      toolsEl.appendChild(el);
    });
  }

  const codeEl = $("codePanel");
  codeEl.innerHTML = "";
  const hasCode = (data.code_blocks || []).length > 0;
  if (!hasCode) {
    codeEl.innerHTML = '<p class="muted">No code in this reply.</p>';
  } else {
    data.code_blocks.forEach((code) => {
      const wrap = document.createElement("div");
      wrap.className = "code-block";
      const pre = document.createElement("pre");
      pre.textContent = code;
      const copy = document.createElement("button");
      copy.className = "copy-btn";
      copy.textContent = "Copy";
      copy.onclick = () => {
        navigator.clipboard.writeText(code);
        copy.textContent = "Copied!";
        setTimeout(() => (copy.textContent = "Copy"), 1500);
      };
      wrap.appendChild(copy);
      wrap.appendChild(pre);
      codeEl.appendChild(wrap);
    });
  }

  if (hasCode) switchTab("code");
  else if (hasCites) switchTab("citations");
  else if (hasTools) switchTab("tools");
  else switchTab("answer");
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach((p) => {
    p.classList.toggle("active", p.id === `panel-${name}`);
  });
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

function connectWs() {
  if (ws && ws.readyState === WebSocket.OPEN) return;
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    setConn(true);
    setStatus("Connected — hold mic to talk");
  };
  ws.onclose = () => {
    setConn(false);
    setStatus("Disconnected — text chat still works");
  };
  ws.onerror = () => setStatus("Connection error");

  ws.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.type === "status") {
      const labels = {
        transcribing: "Transcribing…",
        thinking: "Thinking…",
        speaking: "Speaking…",
        idle: "Ready — hold mic to talk",
      };
      const active = ["transcribing", "thinking", "speaking"].includes(data.status);
      setStatus(labels[data.status] || data.status, active);
    }
    if (data.type === "transcript") appendTranscript("user", data.text);
    if (data.type === "reply") {
      appendTranscript("assistant", data.text);
      showReply(data);
    }
    if (data.type === "audio_out") playAudioBase64(data.audio, data.format || "mp3");
    if (data.type === "error") {
      setStatus(data.message || "Something went wrong");
      appendTranscript("assistant", data.message || "Something went wrong. Please try again.");
      return;
    }
    if (data.type === "cancelled") setStatus("Cancelled");
  };
}

async function uploadPdf(file) {
  if (!file || !file.name.toLowerCase().endsWith(".pdf")) return;

  setStatus("Uploading PDF…", true);
  const form = new FormData();
  form.append("file", file);

  const resp = await fetch(`${API}/api/upload`, { method: "POST", body: form });
  if (!resp.ok) {
    setStatus("Upload failed");
    return;
  }

  const data = await resp.json();
  docId = data.document.id;

  $("docInfo").classList.remove("hidden");
  $("docInfo").innerHTML = `<strong>${escapeHtml(data.document.filename)}</strong><br>${data.document.pages} pages loaded`;

  $("dropzone").querySelector(".dropzone-title").textContent = "PDF loaded";
  $("dropzone").querySelector(".dropzone-hint").textContent = "Click to replace";

  $("pagesPreview").innerHTML = data.pages_preview
    .map((p) => `<div class="page-item"><strong>P${p.page}</strong> ${escapeHtml(p.preview)}</div>`)
    .join("");

  $("hintsCard").classList.remove("hidden");
  $("micBtn").disabled = false;
  $("textInput").disabled = false;
  $("sendBtn").disabled = false;
  $("cancelBtn").disabled = false;
  connectWs();
  setStatus("Ready — ask anything about the PDF");
}

let micMimeType = "audio/webm";

async function startRecording() {
  if (isRecording) return;
  stopAudio();
  if (ws) ws.send(JSON.stringify({ type: "cancel" }));

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    micMimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : MediaRecorder.isTypeSupported("audio/mp4")
          ? "audio/mp4"
          : "";

    const options = micMimeType ? { mimeType: micMimeType } : undefined;
    mediaRecorder = new MediaRecorder(stream, options);
    audioChunks = [];
    const recordStarted = Date.now();

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) audioChunks.push(e.data);
    };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      const durationMs = Date.now() - recordStarted;
      const blob = new Blob(audioChunks, { type: micMimeType || "audio/webm" });

      if (durationMs < 400 || blob.size < 500) {
        setStatus("Hold mic longer — recording was too short");
        return;
      }

      const reader = new FileReader();
      reader.onload = () => {
        const b64 = reader.result.split(",")[1];
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: "audio",
            audio: b64,
            content_type: micMimeType || "audio/webm",
            session_id: sessionId,
            doc_id: docId,
          }));
        }
      };
      reader.readAsDataURL(blob);
    };

    mediaRecorder.start(250);
    isRecording = true;
    window.setWaveActive?.(true);
    $("micBtn").classList.add("recording");
    $("micBtn").querySelector(".mic-label").textContent = "Listening…";
    setStatus("Listening…", true);
  } catch {
    setStatus("Mic permission denied");
  }
}

function stopRecording() {
  if (!isRecording || !mediaRecorder) return;
  mediaRecorder.stop();
  isRecording = false;
  window.setWaveActive?.(false);
  $("micBtn").classList.remove("recording");
  $("micBtn").querySelector(".mic-label").textContent = "Hold";
  setStatus("Processing…", true);
}

async function sendText(textOverride) {
  const text = (textOverride || $("textInput").value).trim();
  if (!text) return;
  stopAudio();
  appendTranscript("user", text);
  if (!textOverride) $("textInput").value = "";
  setStatus("Thinking…", true);

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "text", text, session_id: sessionId, doc_id: docId }));
    return;
  }

  try {
    const resp = await fetch(`${API}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId, doc_id: docId }),
    });
    if (!resp.ok) {
      const err = await resp.text();
      throw new Error(err || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    sessionId = data.session_id || sessionId;
    appendTranscript("assistant", data.reply);
    showReply({ ...data, text: data.reply });
    setStatus("Ready — hold mic to talk");
  } catch (e) {
    setStatus(`Error: ${e.message}`);
    appendTranscript("assistant", "Sorry, something went wrong. Please try again.");
  }
}

// PDF input + drag-drop
$("pdfInput").addEventListener("change", (e) => uploadPdf(e.target.files[0]));

const dropzone = $("dropzone");
dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  uploadPdf(e.dataTransfer.files[0]);
});

// Prompt chips
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    if ($("textInput").disabled) return;
    sendText(chip.textContent);
  });
});

// Mic
$("micBtn").addEventListener("mousedown", startRecording);
$("micBtn").addEventListener("mouseup", stopRecording);
$("micBtn").addEventListener("mouseleave", () => isRecording && stopRecording());
$("micBtn").addEventListener("touchstart", (e) => { e.preventDefault(); startRecording(); });
$("micBtn").addEventListener("touchend", (e) => { e.preventDefault(); stopRecording(); });

$("sendBtn").addEventListener("click", () => sendText());
$("textInput").addEventListener("keydown", (e) => e.key === "Enter" && sendText());

$("cancelBtn").addEventListener("click", () => {
  stopAudio();
  window.setWaveActive?.(false);
  if (ws) ws.send(JSON.stringify({ type: "cancel" }));
  if (isRecording) stopRecording();
  setStatus("Cancelled");
});

window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();

// Waveform on hero device — abstract cyan dithered curves
(function initWaveform() {
  const canvas = document.getElementById("waveCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let phase = 0;
  let active = false;

  function ditherPixel(x, y) {
    return ((x + y * 7) & 3) === 0 ? 0.15 : 0;
  }

  function draw() {
    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);

    // Flowing abstract bands (Monologue-style)
    const layers = [
      { color: "rgba(0, 212, 255, 0.55)", amp: 28, freq: 0.018, yOff: height * 0.38 },
      { color: "rgba(0, 160, 200, 0.35)", amp: 22, freq: 0.024, yOff: height * 0.52 },
      { color: "rgba(0, 100, 140, 0.25)", amp: 18, freq: 0.012, yOff: height * 0.62 },
    ];

    layers.forEach((layer, li) => {
      ctx.beginPath();
      ctx.fillStyle = layer.color;
      ctx.moveTo(0, height);
      for (let x = 0; x <= width; x += 2) {
        const drift = Math.sin(x * layer.freq + phase + li) * layer.amp;
        const ripple = Math.sin(x * 0.06 + phase * 1.4) * (active ? 10 : 4);
        const y = layer.yOff + drift + ripple;
        ctx.lineTo(x, y);
      }
      ctx.lineTo(width, height);
      ctx.closePath();
      ctx.fill();
    });

    // Stipple overlay
    const step = active ? 3 : 4;
    for (let y = 0; y < height; y += step) {
      for (let x = 0; x < width; x += step) {
        if (Math.random() > (active ? 0.72 : 0.88)) {
          ctx.fillStyle = `rgba(255,255,255,${0.08 + ditherPixel(x, y)})`;
          ctx.fillRect(x, y, 1, 1);
        }
      }
    }

    phase += active ? 0.035 : 0.012;
    requestAnimationFrame(draw);
  }

  window.setWaveActive = (on) => { active = on; };
  draw();
})();

// Scroll reveal
(function initReveal() {
  const els = document.querySelectorAll(".reveal");
  if (!els.length) return;
  const io = new IntersectionObserver(
    (entries) => entries.forEach((e) => e.isIntersecting && e.target.classList.add("visible")),
    { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
  );
  els.forEach((el) => io.observe(el));
  // Hero visible immediately
  document.querySelectorAll(".hero .reveal").forEach((el) => {
    setTimeout(() => el.classList.add("visible"), 80);
  });
})();
