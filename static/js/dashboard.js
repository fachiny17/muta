(() => {
  const auto = document.getElementById("auto");
  const updated = document.getElementById("updated");
  if (!auto || !updated) return;

  try { auto.checked = sessionStorage.getItem("muta_auto") === "1"; } catch (error) { auto.checked = false; }
  updated.textContent = "Last loaded " + new Date().toLocaleTimeString();
  let refreshTimer = null;

  function armRefresh() {
    if (refreshTimer !== null) window.clearInterval(refreshTimer);
    refreshTimer = null;
    if (!auto.checked) return;
    refreshTimer = window.setInterval(() => window.location.reload(), 30000);
  }

  auto.addEventListener("change", () => {
    try { sessionStorage.setItem("muta_auto", auto.checked ? "1" : "0"); } catch (error) { /* Refresh still works without storage. */ }
    armRefresh();
  });
  armRefresh();
})();
