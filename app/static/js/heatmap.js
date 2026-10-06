(function () {
  const { api, bindPeriodGroup, escapeHtml, toast } = SM;
  const LEVEL_COLORS = { "very-hot": "#dc3545", hot: "#fd7e14", warm: "#f6b100", cool: "#20c997", cold: "#17a2b8" };
  const GRID = [32, 18];
  let period = "today", mode = "visits", data = null;

  async function load() {
    try {
      data = await api(`/api/analytics/heatmap?period=${period}&mode=${mode}`);
    } catch (e) { return toast(e.message, "danger"); }
    const unit = mode === "visits" ? (period === "today" ? "visitors today" : "visits") : "min avg. dwell";

    document.getElementById("zoneCards").innerHTML = data.zones.map((z) => `
      <div class="col-sm-6 col-lg">
        <div class="stat-card" style="--accent:${LEVEL_COLORS[z.level]}">
          <div class="label mt-0">${escapeHtml(z.name)}</div>
          <div class="value" style="color:var(--sm-text)">${z.value}</div>
          <div class="small text-muted">${unit}</div>
        </div>
      </div>`).join("");

    const map = document.getElementById("heatMap");
    map.querySelectorAll(".zone-box").forEach((el) => el.remove());
    data.zones.forEach((z) => {
      const el = document.createElement("div");
      el.className = `zone-box heat heat-${z.level}`;
      el.style.cssText = `left:${z.x * 100}%;top:${z.y * 100}%;width:${z.w * 100}%;height:${z.h * 100}%;--zc:${LEVEL_COLORS[z.level]}`;
      el.innerHTML = `<span>${escapeHtml(z.name)}</span><span class="visits">${z.value} ${mode === "visits" ? "visits" : "min"}</span>`;
      map.appendChild(el);
    });
    drawDensity();

    document.getElementById("legend").innerHTML = data.levels.map((l) =>
      `<span><span class="legend-swatch" style="background:${LEVEL_COLORS[l.key]}"></span>${escapeHtml(l.label)}${period === "today" ? "" : " /day"}</span>`).join("");

    const colors = { danger: "text-danger", info: "text-info", warning: "text-warning", primary: "text-primary" };
    document.getElementById("insights").innerHTML = data.insights.length ? data.insights.map((i) => `
      <div class="note-box"><div class="fw-bold mb-1"><i class="fa-solid ${escapeHtml(i.icon)} ${colors[i.color] || ""} me-2"></i>${escapeHtml(i.title)}</div>
      <div>${escapeHtml(i.text)}</div></div>`).join("") : `<div class="text-muted">No visits recorded in this period.</div>`;
  }

  /** Smooth presence density from the accumulated grid cells (foot positions). */
  function drawDensity() {
    const canvas = document.getElementById("heatCanvas");
    const show = document.getElementById("densityToggle").checked;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!show || !data || !data.grid.length) return;
    const max = Math.max(...data.grid.map((c) => c.v));
    const cw = canvas.width / GRID[0], ch = canvas.height / GRID[1];
    data.grid.forEach((c) => {
      const intensity = c.v / max;
      const x = (c.x + 0.5) * cw, y = (c.y + 0.5) * ch, r = Math.max(cw, ch) * 1.6;
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, `rgba(255, ${Math.round(200 - 170 * intensity)}, 0, ${0.15 + 0.45 * intensity})`);
      g.addColorStop(1, "rgba(255, 200, 0, 0)");
      ctx.fillStyle = g;
      ctx.fillRect(x - r, y - r, r * 2, r * 2);
    });
  }

  bindPeriodGroup(document.getElementById("periodGroup"), (p) => { period = p; load(); });
  document.getElementById("modeSelect").addEventListener("change", (e) => { mode = e.target.value; load(); });
  document.getElementById("densityToggle").addEventListener("change", drawDensity);
  window.addEventListener("resize", drawDensity);
  load();
})();
