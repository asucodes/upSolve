"use strict";
const $ = (id) => document.getElementById(id);
let handle = "",
  data = null,
  topics = [];
const status = (message) => ($("status").textContent = message);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
async function api(path, options = {}) {
  const response = await fetch("/api/v1" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Please check your input and try again.",
    );
  return body;
}
async function guarded(fn) {
  try {
    await fn();
  } catch (e) {
    status(e.message);
  }
}
function view(name) {
  for (const section of document.querySelectorAll(".view"))
    section.hidden = section.id !== name;
  for (const button of document.querySelectorAll("nav button"))
    button.setAttribute("aria-selected", button.dataset.view === name);
}
for (const b of document.querySelectorAll("nav button"))
  b.onclick = () => view(b.dataset.view);
$("back-today").onclick = () => view("today");
async function savedProfiles() {
  const profiles = await api("/profiles");
  $("profiles").innerHTML =
    '<option value="">Select a profile</option>' +
    profiles
      .map(
        (p) =>
          `<option value="${esc(p.handle)}">${esc(p.handle)}${p.sample ? " (sample)" : ""}</option>`,
      )
      .join("");
}
async function load(h) {
  data = await api(`/profiles/${encodeURIComponent(h)}/dashboard`);
  handle = h;
  localStorage.setItem("upsolve.handle", h);
  $("workspace").hidden = false;
  $("sample-banner").hidden = !data.sample;
  $("sync").disabled = data.sample;
  $("profile-name").textContent = data.handle;
  $("profile-meta").textContent =
    `Last synced ${new Date(data.updated * 1000).toLocaleString()} · ${data.sample ? "Synthetic sample" : "Public Codeforces profile"}`;
  $("model-name").textContent = data.model;
  $("recommendation-note").textContent = data.recommendation_note;
  const a = data.analysis;
  $("stats").innerHTML = [
    ["Problems solved", a.solved.length],
    ["Topics explored", a.topics.filter((t) => t.evidence).length],
    ["Official rating", data.official_rating ?? "Unrated"],
    ["Training target", data.plan.target + " / week"],
  ]
    .map(
      ([label, value]) =>
        `<div class="stat"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`,
    )
    .join("");
  $("recommendations").innerHTML =
    data.recommendations
      .map(
        (p, i) =>
          `<article class="card"><span class="eyebrow">${["WARM-UP", "MAIN CHALLENGE", "STRETCH"][i]}</span><div class="chance">${Math.round(p.probability * 100)}%<small>estimated chance</small></div><h3>${esc(p.name)}</h3><div>${p.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}<span class="tag">${p.rating}</span></div><p>${esc(p.reason)}</p>${data.sample ? '<span class="tag">Sample exercise · no live link</span>' : `<a href="${esc(p.url)}" target="_blank" rel="noopener">Solve on Codeforces ↗</a>`}</article>`,
      )
      .join("") ||
    "<p>No matching unseen problems yet. More practice will refine your estimates.</p>";
  $("topic-bars").innerHTML =
    a.topics
      .slice()
      .sort((a, b) => b.rating - a.rating)
      .map(
        (t) =>
          `<div class="topic-row"><div class="topic-label"><strong>${esc(t.name)}</strong><span>${Math.round(t.rating)}</span></div><div class="meter"><div style="width:${Math.max(3, Math.min(100, (t.rating - 600) / 16))}%"></div></div><small>${t.evidence} distinct problems · ${t.provisional ? "Provisional" : "Established evidence"}</small><br><button class="text-button" data-topic="${esc(t.name)}">Focus on this topic →</button></div>`,
      )
      .join("") ||
    "<p>No rated topic evidence yet. Try a rated problem and sync again.</p>";
  for (const b of document.querySelectorAll("[data-topic]"))
    b.onclick = () => {
      $("focus-one").value = b.dataset.topic;
      view("training");
      $("focus-one").focus();
    };
  const selected = $("chart-topic").value;
  $("chart-topic").innerHTML = a.topics
    .map((t) => `<option>${esc(t.name)}</option>`)
    .join("");
  if (a.topics.some((t) => t.name === selected))
    $("chart-topic").value = selected;
  topicChart();
  chart(
    "contest-chart",
    data.contest_history.map((r) => ({
      time: r.ratingUpdateTimeSeconds,
      rating: r.newRating,
    })),
    "Official rating",
  );
  topics = await api("/topics");
  for (const id of ["focus-one", "focus-two"])
    $(id).innerHTML =
      '<option value="">No focus</option>' +
      topics.map((t) => `<option>${esc(t)}</option>`).join("");
  $("focus-one").value = data.plan.topics[0] || "";
  $("focus-two").value = data.plan.topics[1] || "";
  $("target").value = data.plan.target;
  const monday = new Date();
  monday.setHours(0, 0, 0, 0);
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  const weekly = new Set(
    a.activity
      .filter((s) => s.accepted && s.time * 1000 >= monday.getTime())
      .map((s) => s.problem),
  ).size;
  $("week-progress").textContent =
    `${weekly} of ${data.plan.target} problems solved`;
  $("week-bar").max = data.plan.target;
  $("week-bar").value = weekly;
  heatmap(a.activity);
  await savedProfiles();
  await metrics();
  status(
    `Loaded ${data.handle}. ${data.sample ? "Sample data is separate from real imports." : "Sync after practicing to update your progress."}`,
  );
}
function chart(id, rows, label) {
  if (!rows.length) {
    $(id).textContent = "No history yet.";
    return;
  }
  const values = rows.map((r) => r.rating),
    low = Math.min(...values) - 30,
    high = Math.max(...values) + 30,
    start = rows[0].time,
    end = rows.at(-1).time;
  const points = rows.map(
    (r) =>
      `${45 + ((r.time - start) / Math.max(1, end - start)) * 450},${140 - ((r.rating - low) / (high - low)) * 115}`,
  );
  $(id).innerHTML =
    `<svg class="chart" role="img" aria-label="${esc(label)} from ${Math.round(values[0])} to ${Math.round(values.at(-1))}" viewBox="0 0 520 180"><line x1="45" y1="140" x2="495" y2="140" stroke="#dfe4eb"/><polyline points="${points.join(" ")}" fill="none" stroke="#225ccc" stroke-width="2.5"/><text x="0" y="30" class="chart-label">${Math.round(high)}</text><text x="0" y="142" class="chart-label">${Math.round(low)}</text><text x="45" y="170" class="chart-label">${esc(new Date(start * 1000).toLocaleDateString())}</text><text x="495" y="170" text-anchor="end" class="chart-label">${esc(new Date(end * 1000).toLocaleDateString())}</text></svg>`;
}
function topicChart() {
  chart(
    "topic-chart",
    data.analysis.history.filter((e) => e.topic === $("chart-topic").value),
    $("chart-topic").value + " coach rating",
  );
}
$("chart-topic").onchange = topicChart;
function dateKey(date) {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}
function heatmap(activity) {
  const counts = {};
  for (const row of activity) {
    const key = dateKey(new Date(row.time * 1000));
    counts[key] = (counts[key] || 0) + 1;
  }
  const cells = [];
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - 181);
  for (let i = 0; i < 182; i++) {
    const day = new Date(start);
    day.setDate(day.getDate() + i);
    const n = counts[dateKey(day)] || 0;
    const title = `${day.toLocaleDateString()}: ${n} submissions`;
    cells.push(
      `<button data-level="${n ? Math.min(3, Math.ceil(n / 2)) : 0}" title="${esc(title)}" aria-label="${esc(title)}"></button>`,
    );
  }
  $("heatmap").innerHTML = cells.join("");
  for (const b of $("heatmap").children) {
    b.onfocus = b.onmouseenter = () =>
      ($("activity-detail").textContent = b.title);
  }
}
async function sync(h) {
  $("sync").disabled = true;
  try {
    let job = await api("/sync", {
      method: "POST",
      body: JSON.stringify({ handle: h }),
    });
    while (["queued", "running"].includes(job.status)) {
      status(job.message);
      await new Promise((r) => setTimeout(r, 1600));
      job = await api("/sync/" + job.id);
    }
    if (job.status === "failed") throw new Error(job.message);
    await load(h);
  } finally {
    $("sync").disabled = !!data?.sample;
  }
}
$("handle-form").onsubmit = (e) => {
  e.preventDefault();
  guarded(() => sync($("handle").value.trim()));
};
$("sync").onclick = () => guarded(() => sync(handle));
$("demo").onclick = () =>
  guarded(async () => {
    await api("/demo", { method: "POST" });
    await load("demo");
  });
$("profiles").onchange = (e) => {
  if (e.target.value) guarded(() => load(e.target.value));
};
$("plan-form").onsubmit = (e) => {
  e.preventDefault();
  guarded(async () => {
    const topics = [$("focus-one").value, $("focus-two").value].filter(Boolean);
    await api(`/profiles/${encodeURIComponent(handle)}/plan`, {
      method: "PUT",
      body: JSON.stringify({ topics, target: Number($("target").value) }),
    });
    await load(handle);
    view("today");
    status(
      "Training plan saved. Recommendations now prioritize your focus topics.",
    );
  });
};
async function metrics() {
  const m = await api("/model");
  $("model-metrics").textContent = m.available
    ? `Chronological test: ${m.metrics.test_attempts} attempts · Accuracy ${(m.metrics.accuracy * 100).toFixed(1)}% · Brier ${m.metrics.brier.toFixed(3)} · Elo Brier ${m.metrics.elo_brier.toFixed(3)} · Log loss ${m.metrics.log_loss.toFixed(3)}`
    : "No trained classifier yet. Recommendations use Elo estimates.";
}
$("train-model").onclick = () =>
  guarded(async () => {
    $("train-model").disabled = true;
    try {
      await api("/model/train", { method: "POST" });
      await load(handle);
      status("Classifier trained and evaluated on real imported histories.");
    } finally {
      $("train-model").disabled = false;
    }
  });
guarded(async () => {
  await savedProfiles();
  const saved = localStorage.getItem("upsolve.handle");
  if (saved) await load(saved);
});
