(function () {
  const { api, toast, fmtSeconds, escapeHtml, timeAgo } = SM;
  const feed = document.getElementById("feed");
  if (!feed) return;

  const startBtn = document.getElementById("startBtn");
  const stopBtn = document.getElementById("stopBtn");
  const snapBtn = document.getElementById("snapBtn");
  const pill = document.getElementById("statusPill");
  const placeholder = document.getElementById("feedPlaceholder");
  const select = document.getElementById("cameraSelect");
  let cameraId = Number(feed.dataset.camera);
  let poll = null;

  function setRunning(running) {
    startBtn.disabled = running;
    stopBtn.disabled = !running;
    snapBtn.disabled = !running;
    pill.className = `status-pill ${running ? "online" : "offline"}`;
    pill.innerHTML = `<i class="fa-solid fa-circle fa-2xs"></i> ${running ? "Live" : "Offline"}`;
    const img = feed.querySelector("img");
    if (running && !img) {
      const el = document.createElement("img");
      el.alt = "Live camera feed";
      el.src = `/api/live/stream/${cameraId}?t=${Date.now()}`;
      placeholder.hidden = true;
      feed.appendChild(el);
    } else if (!running && img) {
      img.src = "";
      img.remove();
      placeholder.hidden = false;
    }
  }

  function renderStats(s) {
    document.getElementById("sVisitors").textContent = s.current_visitors ?? 0;
    document.getElementById("sTotal").textContent = s.total_detected ?? 0;
    document.getElementById("sPeak").textContent = s.peak_count ?? 0;
    document.getElementById("sDwell").textContent = fmtSeconds(s.avg_dwell_seconds);
    document.getElementById("pipelineInfo").textContent = s.running
      ? `Detector: ${s.detector} · Tracker: ${s.tracker} · ${s.fps} FPS` : "";
    const log = s.log || [];
    document.getElementById("logList").innerHTML = log.length
      ? log.map((l) => `<div class="log-item"><div class="ic"><i class="fa-solid fa-user"></i></div>
          <div><div class="fw-bold small">Person detected</div>
          <div class="text-muted small">${escapeHtml(l.message)} - ${escapeHtml(l.time)}</div></div></div>`).join("")
      : `<div class="empty-state py-3">No detections yet.</div>`;
  }

  async function refresh() {
    try {
      const s = await api(`/api/live/detect/${cameraId}`);
      renderStats(s);
      setRunning(!!s.running);
      if (s.error) toast(s.error, "danger");
      if (!s.running) stopPolling();
    } catch (e) { /* transient */ }
  }

  async function refreshAlerts() {
    const alerts = await api("/api/system/alerts");
    document.getElementById("liveAlerts").innerHTML = alerts.length
      ? alerts.slice(0, 5).map((a) => `<div class="alert-item ${escapeHtml(a.level)}"><i class="fa-solid ${escapeHtml(a.icon)} ${escapeHtml(a.level)}-i"></i>
          <div><div class="title">${escapeHtml(a.title)}</div><small>${escapeHtml(a.message)} · ${timeAgo(a.created_at)}</small></div></div>`).join("")
      : `<div class="empty-state py-2"><i class="fa-solid fa-circle-check me-1"></i> No active alerts</div>`;
  }

  function startPolling() { stopPolling(); poll = setInterval(refresh, 1500); }
  function stopPolling() { if (poll) clearInterval(poll); poll = null; }

  startBtn.addEventListener("click", async () => {
    startBtn.disabled = true;
    startBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Starting…`;
    try {
      await api(`/api/live/start/${cameraId}`, { method: "POST" });
      setRunning(true);
      startPolling();
      toast("Camera started", "success");
    } catch (e) {
      toast(e.message, "danger");
      startBtn.disabled = false;
    } finally {
      startBtn.innerHTML = `<i class="fa-solid fa-play me-1"></i> Start Camera`;
    }
  });

  stopBtn.addEventListener("click", async () => {
    await api(`/api/live/stop/${cameraId}`, { method: "POST" });
    setRunning(false);
    stopPolling();
    toast("Camera stopped", "secondary");
  });

  snapBtn.addEventListener("click", async () => {
    try {
      const res = await api(`/api/live/snapshot/${cameraId}`, { method: "POST" });
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `snapshot_${Date.now()}.jpg`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { toast(e.message, "danger"); }
  });

  select?.addEventListener("change", () => {
    setRunning(false);
    cameraId = Number(select.value);
    refresh().then(() => { if (!stopBtn.disabled) startPolling(); });
  });

  refresh().then(() => { if (!stopBtn.disabled) startPolling(); });
  refreshAlerts();
  setInterval(refreshAlerts, 15000);
})();
