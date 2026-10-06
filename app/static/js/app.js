/* Shared front-end helpers for every ShopMotion page. */
(function () {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;

  async function api(url, options = {}) {
    const opts = { credentials: "same-origin", ...options, headers: { ...(options.headers || {}) } };
    if (opts.body && typeof opts.body !== "string") {
      opts.body = JSON.stringify(opts.body);
      opts.headers["Content-Type"] = "application/json";
    }
    if (opts.method && opts.method !== "GET") opts.headers["X-CSRFToken"] = csrf;
    const res = await fetch(url, opts);
    const isJson = (res.headers.get("content-type") || "").includes("application/json");
    const data = isJson ? await res.json() : res;
    if (!res.ok) throw new Error((isJson && data.error) || res.statusText);
    return data;
  }

  function toast(message, type = "primary") {
    const area = document.getElementById("toastArea");
    if (!area) return alert(message);
    const el = document.createElement("div");
    el.className = `toast align-items-center text-bg-${type} border-0`;
    el.innerHTML = `<div class="d-flex"><div class="toast-body"></div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
    el.querySelector(".toast-body").textContent = message;
    area.appendChild(el);
    const t = new bootstrap.Toast(el, { delay: 3500 });
    el.addEventListener("hidden.bs.toast", () => el.remove());
    t.show();
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function timeAgo(iso) {
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)} minute${s < 120 ? "" : "s"} ago`;
    if (s < 86400) return `${Math.floor(s / 3600)} hour${s < 7200 ? "" : "s"} ago`;
    return `${Math.floor(s / 86400)} day${s < 172800 ? "" : "s"} ago`;
  }

  function fmtSeconds(sec) {
    sec = Math.round(sec || 0);
    const m = Math.floor(sec / 60), s = sec % 60;
    return m ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
  }

  /** Render a "+12% vs x" delta line into an element. */
  function delta(el, change, suffix) {
    if (!el) return;
    if (change === null || change === undefined) {
      el.className = "delta flat";
      el.innerHTML = `<i class="fa-solid fa-minus"></i> No comparison data`;
      return;
    }
    const up = change >= 0;
    el.className = `delta ${up ? "up" : "down"}`;
    el.innerHTML = `<i class="fa-solid fa-arrow-${up ? "up" : "down"}"></i> ${up ? "+" : ""}${change}% ${escapeHtml(suffix)}`;
  }

  // ---- Chart.js defaults matching the theme
  if (window.Chart) {
    Chart.defaults.font.family = "Nunito, system-ui, sans-serif";
    Chart.defaults.color = "#718096";
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.maintainAspectRatio = false;
  }
  const charts = {};
  function chart(id, config) {
    if (charts[id]) charts[id].destroy();
    const el = document.getElementById(id);
    if (!el) return null;
    charts[id] = new Chart(el, config);
    return charts[id];
  }

  // ---- sidebar toggle
  document.getElementById("sidebarToggle")?.addEventListener("click", () => {
    const shell = document.getElementById("appShell");
    if (window.innerWidth < 992) shell.classList.toggle("sidebar-open");
    else shell.classList.toggle("sidebar-collapsed");
  });
  document.getElementById("sidebarBackdrop")?.addEventListener("click", () =>
    document.getElementById("appShell").classList.remove("sidebar-open"));

  // ---- alerts dropdown
  document.getElementById("alertBell")?.addEventListener("show.bs.dropdown", async () => {
    const menu = document.getElementById("alertMenu");
    try {
      const alerts = await api("/api/system/alerts");
      menu.innerHTML = `<div class="dropdown-header">Active alerts</div>` + (alerts.length
        ? alerts.map((a) => `<div class="px-3 py-2 border-top d-flex gap-2 align-items-start">
            <i class="fa-solid ${escapeHtml(a.icon)} text-${a.level === "danger" ? "danger" : a.level === "warning" ? "warning" : "info"} mt-1"></i>
            <div class="flex-grow-1"><div class="fw-semibold small">${escapeHtml(a.title)}</div>
            <div class="text-muted small">${timeAgo(a.created_at)}</div></div>
            <button class="btn btn-sm btn-link p-0" data-resolve="${a.id}" title="Resolve"><i class="fa-solid fa-check"></i></button></div>`).join("")
        : `<div class="px-3 py-2 text-muted small"><i class="fa-solid fa-circle-check me-1"></i>No active alerts</div>`);
    } catch (e) {
      menu.innerHTML = `<div class="px-3 py-2 text-danger small">${escapeHtml(e.message)}</div>`;
    }
  });
  document.getElementById("alertMenu")?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-resolve]");
    if (!btn) return;
    ev.stopPropagation();
    await api(`/api/system/alerts/${btn.dataset.resolve}/resolve`, { method: "POST" });
    btn.closest(".px-3").remove();
    const badge = document.querySelector(".bell-badge");
    if (badge) {
      const n = parseInt(badge.textContent, 10) - 1;
      n > 0 ? (badge.textContent = n) : badge.remove();
    }
  });

  // Period button groups: <div class="period-group" data-target="fn">
  function bindPeriodGroup(group, onChange) {
    group.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-period]");
      if (!btn) return;
      group.querySelectorAll("[data-period]").forEach((b) => b.classList.toggle("active", b === btn));
      onChange(btn.dataset.period);
    });
  }

  const PALETTE = { primary: "#667eea", success: "#28a745", warning: "#f6b100", danger: "#dc3545", info: "#17a2b8" };

  window.SM = { api, toast, escapeHtml, timeAgo, fmtSeconds, delta, chart, bindPeriodGroup, PALETTE };
})();
