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
        <div class="course-row">
          <button type="button"
                  class="course-select ${selected ? "active" : ""}"
                  data-select-course="${Number(course.id)}">
            <strong>${escapeHTML(course.name)}</strong>
            <small>
              ${escapeHTML(course.language.toUpperCase())}
              · ${Number(course.document_count)} document(s)
            </small>
          </button>

          <button type="button"
                  class="btn btn-danger btn-small"
                  data-delete-course="${Number(course.id)}"
                  aria-label="Delete course: ${escapeHTML(course.name)}">
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.8"
                 stroke-linecap="round"
                 stroke-linejoin="round"
                 aria-hidden="true">
              <path d="M3 6h18"/>
              <path d="M8 6V4h8v2"/>
              <path d="m19 6-1 14H6L5 6"/>
              <path d="M10 10v6"/>
              <path d="M14 10v6"/>
            </svg>
            <span>Delete</span>
          </button>
        </div>
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
    loadDocuments();
  }

  async function loadDocuments() {
    const documentList = $("#document-list");

    if (!activeCourse) {
      documentList.innerHTML =
        '<p class="hint">Select a course to view its documents.</p>';
      return;
    }

    try {
      const data = await api(
        `/api/courses/${activeCourse.id}/documents`
      );

      if (!data.documents.length) {
        documentList.innerHTML =
          '<p class="hint">No documents uploaded yet.</p>';
        return;
      }

      documentList.innerHTML = data.documents.map((document) => `
        <div class="document-item">
          <div>
            <strong>${escapeHTML(document.filename)}</strong>
            <small>Uploaded document</small>
          </div>

          <button type="button"
                  class="btn btn-danger btn-small"
                  data-delete-document="${Number(document.id)}"
                  aria-label="Delete document: ${escapeHTML(document.filename)}">
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.8"
                 stroke-linecap="round"
                 stroke-linejoin="round"
                 aria-hidden="true">
              <path d="M3 6h18"/>
              <path d="M8 6V4h8v2"/>
              <path d="m19 6-1 14H6L5 6"/>
              <path d="M10 10v6"/>
              <path d="M14 10v6"/>
            </svg>
            <span>Delete</span>
          </button>
        </div>
      `).join("");
    } catch (error) {
      documentList.textContent = error.message;
    }
  }

  $("#document-list").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-document]");
    if (!button || !activeCourse) return;

    const documentId = Number(button.dataset.deleteDocument);

    if (!window.confirm("Permanently delete this uploaded document?")) {
      return;
    }

    const courseId = activeCourse.id;

    try {
      setStatus("Deleting document...");

      await api(
        `/api/courses/${courseId}/documents/${documentId}`,
        { method: "DELETE" }
      );

      await refreshCourses();
      selectCourse(courseId);
      await loadDocuments();

      setStatus("Document deleted successfully.");
    } catch (error) {
      setStatus(error.message);
    }
  });

  $("#delete-course").addEventListener("click", async () => {
    if (!activeCourse) return;

    const courseId = activeCourse.id;
    const courseName = activeCourse.name;

    if (!window.confirm(
      `Delete "${courseName}" and all its notes? This cannot be undone.`
    )) {
      return;
    }

    try {
      setStatus(`Deleting ${courseName}...`);

      await api(`/api/courses/${courseId}`, { method: "DELETE" });

      activeCourse = null;
      quizId = null;
      workspace.hidden = true;

      await refreshCourses();
      setStatus("Course and its uploaded notes were deleted.");
    } catch (error) {
      setStatus(error.message);
    }
  });

  courseList.addEventListener("click", async (event) => {
    const deleteButton = event.target.closest("[data-delete-course]");
  
    if (deleteButton) {
      const courseId = Number(deleteButton.dataset.deleteCourse);
      const course = courses.find((item) => item.id === courseId);
    
      if (!course) return;
    
      const confirmed = window.confirm(
        `Delete "${course.name}" and all its uploaded notes? This cannot be undone.`
      );
    
      if (!confirmed) return;
    
      try {
        setStatus(`Deleting ${course.name}...`);
      
        await api(`/api/courses/${courseId}`, { method: "DELETE" });
      
        if (activeCourse && activeCourse.id === courseId) {
          activeCourse = null;
          quizId = null;
          workspace.hidden = true;
        }
      
        await refreshCourses();
        setStatus("Course and its uploaded notes were deleted.");
      } catch (error) {
        setStatus(error.message);
      }
    
      return;
    }
  
    const selectButton = event.target.closest("[data-select-course]");
    if (!selectButton) return;
  
    selectCourse(Number(selectButton.dataset.selectCourse));
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