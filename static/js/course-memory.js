(() => {
  const $ = (selector) => document.querySelector(selector);

  const courseForm = $("#course-form");
  const courseList = $("#course-list");
  const workspace = $("#course-workspace");
  const uploadForm = $("#upload-form");
  const askForm = $("#ask-form");
  const status = $("#cm-status");

  let courses = [];
  let activeCourse = null;
  let quizId = null;
  let recorder = null;
  let microphoneStream = null;
  let audioChunks = [];

  function setStatus(message) {
    status.textContent = message;
  }

  function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[char]);
  }

  async function api(url, options = {}) {
    const headers = { ...(options.headers || {}) };

    if (options.body && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(url, {
      ...options,
      headers: { ...headers, Accept: "application/json" }
    });

    const data = await response.json().catch(() => ({
      ok: false,
      message: "The server returned an unreadable response."
    }));

    if (!response.ok || !data.ok) {
      throw new Error(data.message || "The request failed.");
    }

    return data;
  }

  function renderCourses() {
    if (!courses.length) {
      courseList.innerHTML =
        '<p class="hint">No courses yet. Create your first course above.</p>';
      return;
    }

    courseList.innerHTML = courses.map((course) => {
      const selected = activeCourse && activeCourse.id === course.id;

      return `
        <button type="button"
                class="course-item ${selected ? "active" : ""}"
                data-course-id="${Number(course.id)}">
          <strong>${escapeHTML(course.name)}</strong>
          <small>
            ${escapeHTML(course.language.toUpperCase())}
            · ${Number(course.document_count)} document(s)
          </small>
        </button>
      `;
    }).join("");
  }

  async function refreshCourses() {
    const data = await api("/api/courses");
    courses = data.courses || [];

    if (activeCourse) {
      activeCourse = courses.find(
        (course) => course.id === activeCourse.id
      ) || null;
    }

    renderCourses();

    if (activeCourse) {
      $("#selected-course-info").textContent =
        `${activeCourse.document_count} document(s) uploaded`;
    }
  }

  function selectCourse(courseId) {
    activeCourse = courses.find(
      (course) => course.id === courseId
    ) || null;

    renderCourses();

    if (!activeCourse) return;

    workspace.hidden = false;
    $("#selected-course-name").textContent = activeCourse.name;
    $("#selected-course-info").textContent =
      `${activeCourse.document_count} document(s) uploaded`;

    $("#course-answer-box").hidden = true;
    $("#speakback-box").hidden = true;
    $("#speakback-result").hidden = true;
    quizId = null;

    setStatus(`Selected ${activeCourse.name}. Upload notes or start studying.`);
  }

  courseList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-course-id]");
    if (!button) return;

    selectCourse(Number(button.dataset.courseId));
  });

  courseForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const name = $("#course-name").value.trim();
    const language = $("#course-language").value;

    try {
      setStatus("Creating your course...");

      const data = await api("/api/courses", {
        method: "POST",
        body: JSON.stringify({ name, language })
      });

      await refreshCourses();
      selectCourse(data.course.id);
      courseForm.reset();

      setStatus("Course created successfully.");
    } catch (error) {
      setStatus(error.message);
    }
  });

  uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!activeCourse) {
      setStatus("Select a course first.");
      return;
    }

    const fileInput = $("#document-file");
    if (!fileInput.files.length) {
      setStatus("Choose a PDF or TXT file first.");
      return;
    }

    const formData = new FormData(uploadForm);

    try {
      setStatus("Reading and saving your notes...");

      const data = await api(
        `/api/courses/${activeCourse.id}/documents`,
        { method: "POST", body: formData }
      );

      await refreshCourses();
      selectCourse(activeCourse.id);
      uploadForm.reset();

      setStatus(`${data.filename} was uploaded successfully.`);
    } catch (error) {
      setStatus(error.message);
    }
  });

  askForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!activeCourse) {
      setStatus("Select a course first.");
      return;
    }

    const question = $("#question-input").value.trim();
    if (!question) return;

    $("#course-answer-box").hidden = true;

    try {
      setStatus("Searching your notes and asking N-ATLAS...");

      const data = await api(
        `/api/courses/${activeCourse.id}/ask`,
        {
          method: "POST",
          body: JSON.stringify({ question })
        }
      );

      $("#course-answer").textContent = data.answer;
      $("#course-answer-box").hidden = false;
      setStatus("Answer generated from the available course notes.");
    } catch (error) {
      setStatus(error.message);
    }
  });

  $("#make-question").addEventListener("click", async () => {
    if (!activeCourse) {
      setStatus("Select a course first.");
      return;
    }

    $("#speakback-box").hidden = true;
    $("#speakback-result").hidden = true;

    try {
      setStatus("Preparing an oral question from your notes...");

      const data = await api(
        `/api/courses/${activeCourse.id}/speakback/question`,
        { method: "POST" }
      );

      quizId = data.quiz_id;
      $("#speakback-question").textContent = data.question;
      $("#speakback-box").hidden = false;

      $("#record-start").disabled = false;
      $("#record-stop").disabled = true;

      setStatus("Question ready. Record your answer when you are ready.");
    } catch (error) {
      setStatus(error.message);
    }
  });

  $("#record-start").addEventListener("click", async () => {
    if (!activeCourse || !quizId) {
      setStatus("Generate a SpeakBack question first.");
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setStatus(
        "Audio recording is unavailable in this browser. Open Muta using HTTPS or localhost in a supported browser."
      );
      return;
    }

    try {
      setStatus("Requesting microphone access...");

      microphoneStream = await navigator.mediaDevices.getUserMedia({
        audio: true
      });

      audioChunks = [];

      let options = {};
      if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
        options.mimeType = "audio/webm;codecs=opus";
      }

      recorder = new MediaRecorder(microphoneStream, options);

      recorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size > 0) {
          audioChunks.push(event.data);
        }
      });

      recorder.addEventListener("stop", async () => {
        microphoneStream?.getTracks().forEach((track) => track.stop());
        microphoneStream = null;

        const mimeType = recorder.mimeType || "audio/webm";
        const blob = new Blob(audioChunks, { type: mimeType });

        if (!blob.size) {
          setStatus("No audio was recorded. Please try again.");
          $("#record-start").disabled = false;
          return;
        }

        await submitSpokenAnswer(blob, mimeType);
      });

      recorder.start();

      $("#record-start").disabled = true;
      $("#record-stop").disabled = false;
      setStatus("Recording. Speak clearly, then stop to submit your answer.");
    } catch (error) {
      microphoneStream?.getTracks().forEach((track) => track.stop());
      microphoneStream = null;

      setStatus(
        error.name === "NotAllowedError"
          ? "Microphone access was denied. Allow microphone access and try again."
          : "Could not start recording. Check your microphone and try again."
      );
    }
  });

  $("#record-stop").addEventListener("click", () => {
    if (recorder && recorder.state === "recording") {
      $("#record-stop").disabled = true;
      setStatus("Submitting your recording...");
      recorder.stop();
    }
  });

  async function submitSpokenAnswer(blob, mimeType) {
    if (!activeCourse || !quizId) return;

    const formData = new FormData();
    formData.append("quiz_id", quizId);

    const fileExtension = mimeType.includes("mp4") ? "m4a" : "webm";
    formData.append("audio", blob, `speakback-answer.${fileExtension}`);

    $("#speakback-result").hidden = true;

    try {
      setStatus("Transcribing your answer with N-ATLAS...");

      const data = await api(
        `/api/courses/${activeCourse.id}/speakback/answer`,
        { method: "POST", body: formData }
      );

      $("#spoken-transcript").textContent = data.transcript;
      $("#spoken-feedback").textContent = data.feedback;
      $("#speakback-result").hidden = false;

      setStatus("Your answer has been checked.");
    } catch (error) {
      setStatus(error.message);
    } finally {
      $("#record-start").disabled = false;
      $("#record-stop").disabled = true;
    }
  }

  refreshCourses().catch((error) => {
    setStatus(`Could not load courses: ${error.message}`);
  });
})();