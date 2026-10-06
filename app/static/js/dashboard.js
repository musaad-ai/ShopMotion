(function () {
  const { api, chart, delta, timeAgo, bindPeriodGroup, escapeHtml } = SM;
  const { summary, zones } = window.DASHBOARD;

  document.querySelectorAll("[data-ago]").forEach((el) => (el.textContent = timeAgo(el.dataset.ago)));

  function renderSummary(s) {
    document.getElementById("kpiVisitors").textContent = s.current_visitors;
    document.getElementById("kpiTraffic").textContent = s.today_traffic;
    document.getElementById("kpiDwell").textContent = s.avg_dwell;
    document.getElementById("kpiHot").textContent = s.hot_zones;
    delta(document.getElementById("kpiVisitorsDelta"), s.current_visitors_change, "from yesterday");
    delta(document.getElementById("kpiTrafficDelta"), s.today_traffic_change, "vs average");
    delta(document.getElementById("kpiDwellDelta"), s.avg_dwell_change, "vs last week");
    const hot = document.getElementById("kpiHotDelta");
    hot.className = "delta up";
    hot.innerHTML = s.top_zone
      ? `<i class="fa-solid fa-arrow-up"></i> ${escapeHtml(s.top_zone)} ${s.top_zone_share}% of visits`
      : "No zone data yet";
  }

  // ---- store map
  const map = document.getElementById("storeMap");
  const boxes = {};
  zones.forEach((z) => {
    const el = document.createElement("div");
    el.className = "zone-box";
    el.style.cssText = `left:${z.x * 100}%;top:${z.y * 100}%;width:${z.w * 100}%;height:${z.h * 100}%;--zc:${z.color}`;
    el.innerHTML = `<span>${escapeHtml(z.name)}</span>`;
    map.appendChild(el);
    boxes[z.name] = el;
  });

  function renderOccupancy(live) {
    Object.entries(boxes).forEach(([name, el]) => {
      el.querySelectorAll(".dot").forEach((d) => d.remove());
      const n = Math.min(live[name] || 0, 25);
      for (let i = 0; i < n; i++) {
        const dot = document.createElement("span");
        dot.className = "dot";
        dot.style.left = `${8 + Math.random() * 84}%`;
        dot.style.top = `${10 + Math.random() * 80}%`;
        el.appendChild(dot);
      }
    });
  }

  async function refreshLive() {
    try {
      const [s, z] = await Promise.all([api("/api/analytics/summary"), api("/api/analytics/zones?period=today")]);
      renderSummary(s);
      renderOccupancy(z.live);
      zoneChart(z.visits);
    } catch (e) { /* keep the last good data on screen */ }
  }

  // ---- charts
  async function trend(period) {
    const data = await api(`/api/analytics/trend?period=${period}`);
    chart("trendChart", {
      type: "line",
      data: { labels: data.labels, datasets: [{
        label: "Visitors", data: data.values, tension: 0.4, fill: true,
        borderColor: "#667eea", backgroundColor: "rgba(102,126,234,.1)", pointBackgroundColor: "#667eea", pointRadius: 4,
      }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
  }

  let zoneChartObj = null;
  function zoneChart(visits) {
    const labels = Object.keys(visits);
    const colors = labels.map((n) => (zones.find((z) => z.name === n) || {}).color || "#667eea");
    if (zoneChartObj) {
      zoneChartObj.data.labels = labels;
      zoneChartObj.data.datasets[0].data = Object.values(visits);
      zoneChartObj.update();
      return;
    }
    zoneChartObj = chart("zoneChart", {
      type: "doughnut",
      data: { labels, datasets: [{ data: Object.values(visits), backgroundColor: colors, borderWidth: 0 }] },
      options: { cutout: "50%", plugins: { legend: { position: "bottom" } } },
    });
  }

  renderSummary(summary);
  bindPeriodGroup(document.getElementById("trendPeriod"), trend);
  trend("today");
  refreshLive();
  setInterval(refreshLive, 10000);
})();
