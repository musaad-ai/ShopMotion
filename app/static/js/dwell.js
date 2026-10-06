(function () {
  const { api, chart, delta, bindPeriodGroup, escapeHtml, toast } = SM;
  let period = "week";

  function sub(id, text) {
    const el = document.getElementById(id);
    el.className = "delta flat text-dark";
    el.innerHTML = text ? `<i class="fa-solid fa-clock"></i> ${escapeHtml(text)} average` : "";
  }

  async function load() {
    let d;
    try { d = await api(`/api/analytics/dwell?period=${period}`); } catch (e) { return toast(e.message, "danger"); }
    const k = d.kpis;
    document.getElementById("kAvg").textContent = k.average;
    document.getElementById("kMedian").textContent = k.median;
    document.getElementById("kLongest").textContent = k.longest_zone;
    document.getElementById("kShortest").textContent = k.shortest_zone;
    delta(document.getElementById("kAvgDelta"), k.average_change, "vs previous period");
    delta(document.getElementById("kMedianDelta"), k.median_change, "vs previous period");
    sub("kLongestSub", k.longest_avg);
    sub("kShortestSub", k.shortest_avg);

    chart("distChart", {
      type: "bar",
      data: { labels: d.distribution.labels, datasets: [{ label: "Visits", data: d.distribution.values, backgroundColor: "#667eea", borderRadius: 4 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
    chart("zoneChart", {
      type: "doughnut",
      data: { labels: d.by_zone.labels, datasets: [{ data: d.by_zone.values, backgroundColor: d.by_zone.colors, borderWidth: 0 }] },
      options: { cutout: "50%", plugins: { legend: { position: "bottom" } } },
    });
    chart("trendChart", {
      type: "line",
      data: { labels: d.trend.labels, datasets: [{ label: "Average Dwell Time (minutes)", data: d.trend.values, tension: 0.4, fill: true,
        borderColor: "#667eea", backgroundColor: "rgba(102,126,234,.1)" }] },
      options: { scales: { y: { beginAtZero: true, title: { display: true, text: "Minutes" } } } },
    });

    document.getElementById("zoneCompare").innerHTML = d.zones.map((z) => `
      <div class="col-md-6 col-xl-3"><div class="zone-stat" style="--zc:${z.color}">
        <div class="fw-semibold mb-2"><i class="fa-solid ${escapeHtml(z.icon)} me-2"></i>${escapeHtml(z.name)}</div>
        <div class="row-line"><span>Average Dwell:</span><span>${z.avg}</span></div>
        <div class="row-line"><span>Median Dwell:</span><span>${z.median}</span></div>
        <div class="row-line"><span>Max Recorded:</span><span>${z.max}</span></div>
        <div class="row-line"><span>Engagement Rate:</span><span>${escapeHtml(z.engagement)}</span></div>
      </div></div>`).join("");

    document.getElementById("recs").innerHTML = d.recommendations.length ? d.recommendations.map((r) => `
      <div class="recommend"><div class="ic"><i class="fa-solid ${escapeHtml(r.icon)}"></i></div>
      <div><div class="fw-semibold fs-6">${escapeHtml(r.title)}</div><div class="small">${escapeHtml(r.text)}</div></div></div>`).join("")
      : `<div class="text-muted">No recommendations for this period.</div>`;
  }

  bindPeriodGroup(document.getElementById("periodGroup"), (p) => { period = p; load(); });
  load();
})();
