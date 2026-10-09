(() => {
  // Recording controls live here so transcription quality can be tuned in one place.
  const AUDIO_BITRATE = 24000;
  const AUDIO_CONSTRAINTS = Object.freeze({
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true
  });

  const $ = (id) => document.getElementById(id);
  const MAX_SECONDS = Object.freeze({ question: 60, summary: 180 });
  const LANGUAGE_TAGS = Object.freeze({ en: "en", ha: "ha", yo: "yo", ig: "ig" });
  let recorder = null;
  let stream = null;
  let chunks = [];
  let recordingTimer = null;
  let processingTimer = null;
  let interactionId = null;
  let mime = "";
  let mode = "question";
  let lastTranscript = "";
  let lastAnswer = "";
  let rating = null;
  let taskDone = null;
  let submitting = false;
  let appState = "consent";
  let processingStartedAt = 0;
  let audioContext = null;
  let analyser = null;
  let sourceNode = null;
  let meterFrame = 0;

  function setState(next) {
    appState = next;
    document.body.dataset.mutaState = next;
  }

  function toast(message, type = "info") {
    const root = $("toast-root");
    const el = document.createElement("div");
    el.className = "toast " + type;
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.textContent = message;
    root.replaceChildren(el);
    window.setTimeout(() => { if (el.isConnected) el.remove(); }, 4200);
  }

  function download(content, filename) {
    const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function showTutor() {
    $("consent").hidden = true;
    $("tutor").hidden = false;
    setState("idle");
  }

  const status = (message) => { $("status").textContent = message; };

  try {
    if (localStorage.getItem("cv_consent") === "1") showTutor();
  } catch (error) {
  }

  $("agree").addEventListener("click", () => {
    try { localStorage.setItem("cv_consent", "1"); } catch (error) {}
    showTutor();
  });

  function gatewayState(ok, unreachable = false) {
    const chip = $("gw");
    chip.textContent = ok ? "N-ATLAS online" : (unreachable ? "Server unreachable" : "N-ATLAS offline");
    chip.className = "chip " + (ok ? "ok" : "bad");
    $("offline").hidden = !!ok;
  }

  fetch("/health", { headers: { Accept: "application/json" } })
    .then((response) => {
      if (!response.ok) throw new Error("health check failed");
      return response.json();
    })
    .then((health) => gatewayState(!!(health && health.gateway && health.gateway.ok)))
    .catch(() => gatewayState(false, true));

  function setModeButtons() {
    document.querySelectorAll("#mode button").forEach((button) => {
      const selected = button.dataset.m === mode;
      button.classList.toggle("sel", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
  }

  document.querySelectorAll("#mode button").forEach((button) => {
    button.addEventListener("click", () => {
      if (["requesting", "recording", "processing"].includes(appState)) return;
      mode = button.dataset.m;
      setModeButtons();
      status(mode === "summary"
        ? "Record a short lesson, up to 3 minutes, then tap Stop."
        : "Tap the microphone, speak clearly, then tap Stop when you're done.");
    });
  });

  const mmss = (seconds) => String(Math.floor(seconds / 60)).padStart(2, "0") + ":" + String(seconds % 60).padStart(2, "0");

  function pickMime() {
    if (!window.MediaRecorder || typeof MediaRecorder.isTypeSupported !== "function") return "";
    const options = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    return options.find((type) => MediaRecorder.isTypeSupported(type)) || "";
  }

  function stopMeter() {
    if (meterFrame) window.cancelAnimationFrame(meterFrame);
    meterFrame = 0;
    try { if (sourceNode) sourceNode.disconnect(); } catch (error) {}
    sourceNode = null;
    analyser = null;
    if (audioContext) {
      const contextToClose = audioContext;
      audioContext = null;
      try { contextToClose.close().catch(() => {}); } catch (error) {}
    }
    document.querySelectorAll("#level-meter span").forEach((bar) => { bar.style.height = "5px"; });
  }

  function startMeter(activeStream) {
    stopMeter();
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    try {
      audioContext = new AudioContextClass();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      sourceNode = audioContext.createMediaStreamSource(activeStream);
      sourceNode.connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      const bars = Array.from(document.querySelectorAll("#level-meter span"));
      const draw = () => {
        if (!analyser || appState !== "recording") return;
        analyser.getByteTimeDomainData(samples);
        let sum = 0;
        for (let index = 0; index < samples.length; index += 1) {
          const value = (samples[index] - 128) / 128;
          sum += value * value;
        }
        const level = Math.min(1, Math.sqrt(sum / samples.length) * 4.5);
        bars.forEach((bar, index) => {
          const variation = 0.35 + Math.abs(Math.sin((index + 1) * 1.7)) * 0.65;
          bar.style.height = Math.max(4, 4 + level * 22 * variation) + "px";
        });
        meterFrame = window.requestAnimationFrame(draw);
      };
      if (audioContext.state === "suspended") audioContext.resume().catch(() => {});
      draw();
    } catch (error) {
      stopMeter();
    }
  }

  function updateRecordingUI(recording) {
    document.body.classList.toggle("is-recording", recording);
    $("mic").classList.toggle("rec", recording);
    $("mic").setAttribute("aria-pressed", String(recording));
    $("mic").setAttribute("aria-label", recording ? "Stop recording" : "Start recording");
    $("recording-status-bar").hidden = !recording;
    $("recording-status-label").textContent = recording ? "Recording" : "Recording stopped";
  }

  function microphoneError(error) {
    const name = error && error.name;
    if (name === "NotAllowedError" || name === "SecurityError") {
      return "Microphone permission is blocked. Allow microphone access in your browser settings, then try again.";
    }
    if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      return "No microphone was found. Connect or enable a microphone, then try again.";
    }
    if (name === "NotReadableError" || name === "TrackStartError") {
      return "The microphone is busy in another app. Close that app and try again.";
    }
    return "Muta could not start the microphone. Check browser permissions and try again.";
  }

  async function startRecording() {
    if (["requesting", "recording", "processing"].includes(appState)) return;
    if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
      toast("Microphone access needs a supported browser and a secure page (HTTPS or localhost).", "error");
      status("This browser cannot access the microphone. Open Muta over HTTPS or use a supported browser.");
      return;
    }
    if (!window.MediaRecorder) {
      toast("Audio recording is not supported by this browser. Try a current version of Chrome, Firefox or Safari.", "error");
      return;
    }

    setState("requesting");
    $("mic").disabled = true;
    status("Allow microphone access when your browser asks. Your recording is deleted after processing.");
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: AUDIO_CONSTRAINTS });
      mime = pickMime();
      chunks = [];
      const options = mime ? { mimeType: mime, audioBitsPerSecond: AUDIO_BITRATE } : { audioBitsPerSecond: AUDIO_BITRATE };
      recorder = new MediaRecorder(stream, options);
      recorder.addEventListener("dataavailable", (event) => { if (event.data && event.data.size) chunks.push(event.data); });
      recorder.addEventListener("stop", sendRecording, { once: true });
      recorder.addEventListener("error", () => {
        finishStream();
        $("mic").disabled = false;
        setState("idle");
        updateRecordingUI(false);
        toast("The browser stopped the recording unexpectedly. Please record again.", "error");
        status("Recording interrupted. Try again when you're ready.");
      }, { once: true });
      recorder.start();
      setState("recording");
      $("mic").disabled = false;
      updateRecordingUI(true);
      $("recording-duration").textContent = mmss(0);
      status("Recording. Speak naturally, then tap Stop when you're finished.");
      startMeter(stream);
      let seconds = 0;
      recordingTimer = window.setInterval(() => {
        seconds += 1;
        $("recording-duration").textContent = mmss(seconds);
        if (seconds >= MAX_SECONDS[mode]) stopRecording();
      }, 1000);
    } catch (error) {
      finishStream();
      $("mic").disabled = false;
      setState("idle");
      updateRecordingUI(false);
      const message = microphoneError(error);
      status(message);
      toast(message, "error");
    }
  }

  function finishStream() {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    stopMeter();
  }

  function stopRecording() {
    if (!recorder || recorder.state !== "recording") return;
    if (recordingTimer) window.clearInterval(recordingTimer);
    recordingTimer = null;
    setState("processing");
    updateRecordingUI(false);
    status("Recording complete. Preparing your upload...");
    try { recorder.stop(); } catch (error) {
      finishStream();
      setState("idle");
      $("mic").disabled = false;
      toast("The recording could not be completed. Please try again.", "error");
    }
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stopMeter();
  }

  function elapsedLabel(seconds) {
    return seconds === 1 ? "1 second" : seconds + " seconds";
  }

  function processingStage(seconds) {
    if (seconds < 4) return "Sending your recording";
    if (seconds < 14) return "Listening to your voice";
    if (seconds < 35) return "Preparing your answer";
    return "Still working — the first request after idle can take longer";
  }

  function beginProcessing() {
    $("processing").hidden = false;
    $("processing").setAttribute("aria-busy", "true");
    processingStartedAt = window.performance && performance.now ? performance.now() : Date.now();
    $("elapsed-counter").textContent = "0 seconds";
    $("processing-stage").textContent = processingStage(0);
    setState("processing");
    if (processingTimer) window.clearInterval(processingTimer);
    processingTimer = window.setInterval(() => {
      const now = window.performance && performance.now ? performance.now() : Date.now();
      const seconds = Math.max(0, Math.floor((now - processingStartedAt) / 1000));
      $("elapsed-counter").textContent = elapsedLabel(seconds);
      $("processing-stage").textContent = processingStage(seconds);
    }, 1000);
  }

  function endProcessing() {
    if (processingTimer) window.clearInterval(processingTimer);
    processingTimer = null;
    $("processing").hidden = true;
    $("processing").setAttribute("aria-busy", "false");
  }

  function fallbackMessage(httpStatus) {
    if (httpStatus === 400) return "Muta could not accept that recording. Check your language selection and record again.";
    if (httpStatus === 413) return "That recording is too large to upload. Record a shorter clip and try again.";
    if (httpStatus === 429) return "You've reached the current usage limit. Please wait a while before trying again.";
    if (httpStatus >= 500) return "The AI service encountered a problem. Please try again in a little while.";
    return "Muta could not process that recording. Please try again.";
  }

  function friendlyMessage(data, httpStatus) {
    const message = data && typeof data.message === "string" ? data.message.trim() : "";
    if (httpStatus === 413) return "That recording is too large to upload. Record a shorter clip and try again.";
    if (httpStatus === 429) return message || fallbackMessage(httpStatus);
    if (httpStatus >= 500) return "The AI service encountered a problem. Please try again in a little while.";
    return message || fallbackMessage(httpStatus || 0);
  }

  async function sendRecording() {
    const activeRecorder = recorder;
    const type = ((activeRecorder && activeRecorder.mimeType) || mime || "audio/webm").split(";")[0];
    const blob = new Blob(chunks, { type });
    finishStream();
    if (blob.size < 1500) {
      endProcessing();
      setState("idle");
      $("mic").disabled = false;
      status("No clear audio was captured. Try speaking a little longer and closer to the microphone.");
      toast("That recording was too short. Please speak for a little longer and try again.", "error");
      return;
    }

    const extension = type.includes("mp4") ? "m4a" : (type.includes("ogg") ? "ogg" : "webm");
    const form = new FormData();
    form.append("audio", blob, "recording." + extension);
    form.append("language", $("lang").value);
    form.append("mode", mode);
    form.append("consent", "1");
    $("mic").disabled = true;
    $("out").hidden = true;
    beginProcessing();
    status("Your recording has been sent. Muta is transcribing it and preparing a response.");

    try {
      const response = await fetch("/api/ask", { method: "POST", body: form, headers: { Accept: "application/json" } });
      let data;
      try { data = await response.json(); }
      catch (error) { data = { ok: false, message: "The server sent an unexpected reply. Please try again." }; }
      if (!response.ok && (!data || data.ok !== false)) data = { ok: false, message: friendlyMessage(data, response.status) };
      if (data && data.ok === false) data.message = friendlyMessage(data, response.status);
      renderResult(data, response.status);
    } catch (error) {
      endProcessing();
      setState("idle");
      $("mic").disabled = false;
      gatewayState(false, true);
      const message = "Muta could not reach the server. Check your connection, then try again.";
      status(message);
      toast(message, "error");
    }
  }

  function renderResult(data, httpStatus = 200) {
    endProcessing();
    $("out").hidden = false;
    lastTranscript = data && typeof data.transcript === "string" ? data.transcript : "";
    $("transcription-text").textContent = lastTranscript || "No transcript was returned. You can try recording again.";
    $("word-count").textContent = String(lastTranscript.split(/\s+/).filter(Boolean).length);
    $("answer-title").textContent = mode === "summary" ? "Lesson summary" : "Answer";
    $("answer").lang = LANGUAGE_TAGS[$("lang").value] || "en";
    resetSurvey();

    if (data && data.ok) {
      interactionId = data.interaction_id;
      lastAnswer = typeof data.answer === "string" ? data.answer : "";
      $("answer").textContent = lastAnswer || "No answer was returned. Please try again.";
      $("fb").hidden = false;
      const latency = Number(data.latency_ms);
      const doneMessage = Number.isFinite(latency) && latency >= 0
        ? `Done in ${(latency / 1000).toFixed(1)} seconds. Please rate the answer below.`
        : "Your answer is ready. Please rate it below.";
      status(doneMessage);
      setState("answered");
    } else {
      interactionId = null;
      lastAnswer = "";
      const message = friendlyMessage(data, httpStatus);
      $("answer").textContent = message;
      $("fb").hidden = true;
      status(message);
      toast(message, "error");
      setState("idle");
    }
    $("mic").disabled = false;
  }

  function resetSurvey() {
    rating = null;
    taskDone = null;
    submitting = false;
    $("fbmsg").textContent = "";
    $("fb-submit").hidden = true;
    $("fb-done").hidden = true;
    document.querySelectorAll("#fb button").forEach((button) => {
      button.classList.remove("sel");
      button.setAttribute("aria-pressed", "false");
    });
    setSurveyDisabled(false);
  }

  function mark(group, selectedButton) {
    document.querySelectorAll(group + " button").forEach((button) => {
      const selected = button === selectedButton;
      button.classList.toggle("sel", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
  }

  function setSurveyDisabled(disabled) {
    document.querySelectorAll("#stars button, #task button, #fb-submit").forEach((button) => {
      button.disabled = disabled;
    });
  }

  async function submitSurvey() {
    if (!interactionId || submitting || rating === null) return;
    submitting = true;
    setSurveyDisabled(true);
    $("fbmsg").textContent = "Saving your feedback…";
    const payload = { interaction_id: interactionId, rating };
    if (taskDone !== null) payload.task_completed = taskDone;
    try {
      const response = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload)
      });
      let result = {};
      try { result = await response.json(); } catch (error) {}
      if (!response.ok || !result.ok) throw new Error(result && result.message ? result.message : "Could not save the survey. Please try again.");
      $("fbmsg").textContent = "";
      $("fb").hidden = true;
      $("fb-done").hidden = false;
      toast("Survey successfully saved! Thank you.", "success");
      interactionId = null;
      submitting = false;
      setState("complete");
    } catch (error) {
      submitting = false;
      setSurveyDisabled(false);
      const message = error && error.message && !/Unexpected token|JSON/i.test(error.message)
        ? error.message
        : "Muta could not save your feedback. Check your connection and try again.";
      $("fbmsg").textContent = message;
      toast(message, "error");
    }
  }

  document.querySelectorAll("#stars button").forEach((button) => {
    button.addEventListener("click", () => {
      if (submitting) return;
      rating = Number(button.dataset.r);
      mark("#stars", button);
      if (taskDone !== null) submitSurvey();
      else $("fb-submit").hidden = false;
    });
  });

  document.querySelectorAll("#task button").forEach((button) => {
    button.addEventListener("click", () => {
      if (submitting) return;
      taskDone = button.dataset.t === "1";
      mark("#task", button);
      if (rating !== null) submitSurvey();
    });
  });
  $("fb-submit").addEventListener("click", submitSurvey);

  $("copy").addEventListener("click", async () => {
    if (!lastAnswer) { toast("There is no answer to copy yet.", "error"); return; }
    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(lastAnswer);
      toast("Answer copied.", "success");
    } catch (error) {
      toast("Copy is unavailable in this browser. Use Download answer instead.", "error");
    }
  });
  $("dl-transcript").addEventListener("click", () => lastTranscript ? download(lastTranscript, "muta-transcript.txt") : toast("There is no transcript to download yet.", "error"));
  $("dl-answer").addEventListener("click", () => lastAnswer ? download(lastAnswer, "muta-answer.txt") : toast("There is no answer to download yet.", "error"));

  $("mic").addEventListener("click", () => {
    if (appState === "recording" && recorder && recorder.state === "recording") stopRecording();
    else if (!$("mic").disabled) startRecording();
  });
})();
