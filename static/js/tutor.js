(() => {
  const $ = (id) => document.getElementById(id);
  const MAX_S = { question: 60, summary: 180 };
  let recorder, stream, chunks = [], timer, interactionId = null, mime = "", mode = "question", lastTranscript = "", lastAnswer = "";
  let rating = null, taskDone = null, submitting = false;   // survey state

  // ---- helpers carried over from NexLearn ----
  function toast(msg, type = "info") {
    const el = document.createElement("div");
    el.className = "toast " + type;
    el.textContent = msg;               // textContent, never innerHTML (NexLearn's modal used innerHTML)
    $("toast-root").replaceChildren(el);
    setTimeout(() => el.remove(), 3500);
  }
  function download(content, filename) {
    const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: filename });
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  }
  $("theme-toggle").onclick = () => document.body.classList.toggle("light-theme");

  // ---- consent + status ----
  const status = (t) => { $("status").textContent = t; };
  const showTutor = () => { $("consent").hidden = true; $("tutor").hidden = false; };
  try { if (localStorage.getItem("cv_consent") === "1") showTutor(); } catch (e) {}
  $("agree").onclick = () => { try { localStorage.setItem("cv_consent", "1"); } catch (e) {} showTutor(); };

  fetch("/health").then(r => r.json()).then(h => {
    const ok = h.gateway && h.gateway.ok;
    $("gw").textContent = ok ? "N-ATLAS online" : "N-ATLAS offline";
    $("gw").className = "chip " + (ok ? "ok" : "bad");
    $("offline").hidden = !!ok;
  }).catch(() => { $("gw").textContent = "server unreachable"; $("gw").className = "chip bad"; });

  document.querySelectorAll("#mode button").forEach(b => b.onclick = () => {
    mode = b.dataset.m;
    document.querySelectorAll("#mode button").forEach(x => x.classList.toggle("sel", x === b));
    status(mode === "summary" ? "Record a short lesson (up to 3 minutes), then tap to stop."
                              : "Tap the microphone, speak, then tap again to stop.");
  });

  // ---- recording (MediaRecorder, as in NexLearn) ----
  function pickMime() {
    const opts = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    return opts.find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
  }
  const mmss = (s) => String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");

  async function start() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast("Audio recording is not supported in this browser, or the page is not on https/localhost.", "error"); return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    } catch (e) { toast("Could not access the microphone. Check browser permissions.", "error"); return; }
    mime = pickMime(); chunks = [];
    const opts = mime ? { mimeType: mime, audioBitsPerSecond: 24000 } : { audioBitsPerSecond: 24000 }; // small uploads for weak networks
    recorder = new MediaRecorder(stream, opts);
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = send;
    recorder.start();
    document.body.classList.add("is-recording"); $("mic").classList.add("rec");
    $("recording-status-bar").style.display = "flex";
    let s = 0; $("recording-duration").textContent = mmss(0); status("Recording...");
    timer = setInterval(() => { s++; $("recording-duration").textContent = mmss(s); if (s >= MAX_S[mode]) stop(); }, 1000);
  }

  function stop() {
    clearInterval(timer);
    if (recorder && recorder.state !== "inactive") recorder.stop();
    stream && stream.getTracks().forEach(t => t.stop());
    document.body.classList.remove("is-recording"); $("mic").classList.remove("rec");
    $("recording-status-bar").style.display = "none";
  }

  async function send() {
    const type = (recorder.mimeType || mime || "audio/webm").split(";")[0];
    const blob = new Blob(chunks, { type });
    if (blob.size < 1500) { toast("That was too short. Please try again.", "error"); status(""); return; }
    const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
    const fd = new FormData();
    fd.append("audio", blob, "recording." + ext);
    fd.append("language", $("lang").value); fd.append("mode", mode); fd.append("consent", "1");
    $("mic").disabled = true;
    status(`Processing (${Math.round(blob.size / 1024)} KB uploaded). This can take several seconds...`);
    try {
      const r = await fetch("/api/ask", { method: "POST", body: fd });
      let d;
      try { d = await r.json(); } catch (e) { d = { ok: false, message: "The server sent an unexpected reply. Please try again." }; }
      render(d);
    } catch (e) { toast("Could not reach the server. Check your connection and try again.", "error"); status(""); }
    $("mic").disabled = false;
  }

  function render(d) {
    $("out").hidden = false;
    lastTranscript = d.transcript || "";
    $("transcription-text").textContent = lastTranscript || "(no transcript)";
    $("word-count").textContent = lastTranscript.split(/\s+/).filter(Boolean).length;
    $("answer-title").textContent = mode === "summary" ? "Lesson summary" : "Answer";
    resetSurvey();
    if (d.ok) {
      interactionId = d.interaction_id; lastAnswer = d.answer;
      $("answer").textContent = d.answer; $("fb").hidden = false;
      status(`Done in ${(d.latency_ms / 1000).toFixed(1)}s. Please rate the answer below.`);
    } else {
      interactionId = null; lastAnswer = "";
      $("answer").textContent = d.message || "Something went wrong. Please try again.";
      $("fb").hidden = true; status("");
    }
  }

  // ---- survey: choose both answers -> saved once -> survey disappears -> thank-you message ----
  function resetSurvey() {
    rating = null; taskDone = null; submitting = false;
    $("fbmsg").textContent = "";
    $("fb-submit").hidden = true;
    $("fb-done").hidden = true;
    document.querySelectorAll("#fb button").forEach(b => b.classList.remove("sel"));
  }

  function mark(group, btn) {
    document.querySelectorAll(group + " button").forEach(b => b.classList.toggle("sel", b === btn));
  }

  async function submitSurvey() {
    if (!interactionId || submitting || rating === null) return;
    submitting = true;
    const payload = { interaction_id: interactionId, rating };
    if (taskDone !== null) payload.task_completed = taskDone;
    try {
      const r = await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload) });
      if (!r.ok) throw new Error("save failed");
      $("fb").hidden = true;            // the questions disappear
      $("fb-done").hidden = false;      // permanent thank-you message
      toast("Survey successfully saved! Thank you.", "success");
      interactionId = null;             // this answer has now been rated
    } catch (e) {
      submitting = false;
      toast("Could not save the survey. Please try again.", "error");
    }
  }

  document.querySelectorAll("#stars button").forEach(b => b.onclick = () => {
    rating = +b.dataset.r; mark("#stars", b);
    if (taskDone !== null) submitSurvey();      // both answered -> save automatically
    else $("fb-submit").hidden = false;         // otherwise offer "rating only"
  });
  document.querySelectorAll("#task button").forEach(b => b.onclick = () => {
    taskDone = b.dataset.t === "1"; mark("#task", b);
    if (rating !== null) submitSurvey();
  });
  $("fb-submit").onclick = submitSurvey;

  // ---- copy / download (from NexLearn) ----
  $("copy").onclick = () => navigator.clipboard.writeText(lastAnswer).then(() => toast("Copied.", "success"), () => toast("Copy failed.", "error"));
  $("dl-transcript").onclick = () => lastTranscript ? download(lastTranscript, "transcript.txt") : toast("Nothing to download yet.", "error");
  $("dl-answer").onclick = () => lastAnswer ? download(lastAnswer, "answer.txt") : toast("Nothing to download yet.", "error");

  $("mic").onclick = () => (recorder && recorder.state === "recording") ? stop() : start();
})();