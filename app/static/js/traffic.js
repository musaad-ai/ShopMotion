(function () {
  const { api, chart, delta, bindPeriodGroup, escapeHtml, toast } = SM;
  let query = "period=today";
  let last = null;

  async function load() {
    try {
      last = await api(`/api/analytics/traffic?${query}`);
    } catch (e) { return toast(e.message, "danger"); }
    const k = last.kpis;
    document.getElementById("kTotal").textContent = k.total_visitors.toLocaleString();
    document.getElementById("kPerHour").textContent = k.avg_per_hour;
    document.getElementById("kPeak").textContent = k.peak_hour;
    document.getElementById("kEntry").textContent = `${k.entry_rate}%`;
    delta(document.getElementById("kTotalDelta"), k.total_change, "vs last period");
    delta(document.getElementById("kPerHourDelta"), k.avg_per_hour_change, "vs last period");

    chart("trendChart", {
      type: "line",
      data: { labels: last.trend.labels, datasets: [{ label: "Visitors", data: last.trend.values, tension: 0.35, fill: true,
        borderColor: "#667eea", backgroundColor: "rgba(102,126,234,.12)", pointRadius: 3 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
    chart("hourlyChart", {
      type: "bar",
      data: { labels: last.hourly.labels, datasets: [{ label: "Avg. visitors", data: last.hourly.values,
        backgroundColor: "#667eea", borderRadius: 4 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
    chart("weeklyChart", {
      type: "radar",
      data: { labels: last.weekly.labels, datasets: [{ label: "Last 7 days", data: last.weekly.values,
        borderColor: "#667eea", backgroundColor: "rgba(102,126,234,.2)", pointBackgroundColor: "#667eea" }] },
      options: { scales: { r: { beginAtZero: true } } },
    });

    document.getElementById("comparisonBody").innerHTML = last.comparison.map((r) => {
      const c = r.change;
      const pill = c === null ? `<span class="text-muted">—</span>`
        : `<span class="change-pill ${c >= 0 ? "up" : "down"}"><i class="fa-solid fa-arrow-${c >= 0 ? "up" : "down"}"></i> ${c >= 0 ? "+" : ""}${c}%</span>`;
      return `<tr><td class="fw-bold">${escapeHtml(r.metric)}</td><td>${escapeHtml(r.current)}</td><td>${escapeHtml(r.previous)}</td><td>${pill}</td></tr>`;
    }).join("");

    document.getElementById("insights").innerHTML = last.insights.length ? last.insights.map((i) =>
      `<div class="insight"><div class="ic"><i class="fa-solid ${escapeHtml(i.icon)}"></i></div>
       <div><div class="fw-bold">${escapeHtml(i.title)}</div><div class="small">${escapeHtml(i.text)}</div></div></div>`).join("")
      : `<div class="text-muted">Not enough data for insights yet.</div>`;
  }

  bindPeriodGroup(document.getElementById("periodGroup"), (p) => { query = `period=${p}`; load(); });

  document.getElementById("rangeForm").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const s = document.getElementById("rangeStart").value, e = document.getElementById("rangeEnd").value;
    document.querySelectorAll("#periodGroup [data-period]").forEach((b) => b.classList.remove("active"));
    query = `start=${encodeURIComponent(s)}&end=${encodeURIComponent(e)}`;
    load();
  });

  document.getElementById("exportBtn").addEventListener("click", () => {
    if (!last) return;
    const rows = [["Period", "Visitors"], ...last.trend.labels.map((l, i) => [l, last.trend.values[i]])];
    const blob = new Blob([rows.map((r) => r.join(",")).join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "traffic_trend.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  });

  load();
})();
