"use strict";
const $ = (id) => document.getElementById(id);
let handle = "",
  data = null,
  topics = [];
let loadVersion = 0;
let activeView =
  location.hash.slice(1) ||
  (location.pathname === "/problemset"
    ? "problemset"
    : location.pathname === "/gym"
      ? "gym"
      : "today");
const status = (message) => ($("status").textContent = message);
function ratingColor(rating) {
  if (rating == null || rating < 1200) return "#777";
  if (rating < 1400) return "#008000";
  if (rating < 1600) return "#038a8a";
  if (rating < 1900) return "#0000aa";
  if (rating < 2100) return "#a0a";
  if (rating < 2400) return "#b66b00";
  return "#c00";
}
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
  if (!["today", "problemset", "gym", "insights", "training"].includes(name))
    name = "today";
  activeView = name;
  history.replaceState(null, "", "#" + name);
  $("workspace").hidden = !data && !["problemset", "gym"].includes(name);
  for (const el of document.querySelectorAll(
    ".profile-head, #stats, #coverage-note",
  ))
    el.hidden = !data;
  for (const section of document.querySelectorAll(".view"))
    section.hidden = section.id !== name;
  for (const button of document.querySelectorAll("nav button"))
    button.setAttribute("aria-selected", button.dataset.view === name);
  if (name === "problemset") guarded(() => loadProblems());
  if (name === "gym") guarded(() => loadGym());
  if (!data && !["problemset", "gym"].includes(name))
    status(
      "Select or connect a profile first. You can browse the Problemset without one.",
    );
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
  $("profiles").value = handle;
}
async function load(h) {
  const version = ++loadVersion;
  const loaded = await api(`/profiles/${encodeURIComponent(h)}/dashboard`);
  if (version !== loadVersion) return;
  data = loaded;
  handle = h;
  localStorage.setItem("upsolve.handle", h);
  $("workspace").hidden = false;
  $("sample-banner").hidden = !data.sample;
  $("sync").disabled = data.sample;
  $("profile-name").textContent = data.handle;
  $("profile-name").style.color = ratingColor(data.official_rating);
  $("profile-meta").textContent =
    `Last synced ${new Date(data.updated * 1000).toLocaleString()} · ${data.sample ? "Synthetic sample" : "Public Codeforces profile"}`;
  $("model-name").textContent = data.model;
  $("recommendation-note").textContent = data.recommendation_note;
  const a = data.analysis;
  $("stats").innerHTML = [
    [
      data.sample ? "Sample problems solved" : "Problems solved (public API)",
      a.solved.length,
    ],
    ["Topics explored", a.topics.filter((t) => t.evidence).length],
    ["Official rating", data.official_rating ?? "Unrated"],
    ["Training target", data.plan.target + " / week"],
  ]
    .map(
      ([label, value]) =>
        `<div class="stat"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`,
    )
    .join("");
  $("coverage-note").innerHTML = data.sample
    ? ""
    : `Counted from ${data.submission_coverage.submissions} imported submissions. This may differ from your full Codeforces profile total. <a href="${esc(data.submission_coverage.profile_url)}" target="_blank" rel="noopener">View Codeforces profile</a>.`;
  $("recommendations").innerHTML =
    '<table class="problems-table"><thead><tr><th scope="col">#</th><th scope="col">Problem</th><th scope="col">Rating</th><th scope="col">Practice estimate</th></tr></thead><tbody>' +
    (data.recommendations
      .map(
        (p, i) =>
          `<tr><td class="problem-index">${i + 1}</td><td>${data.sample ? `<strong>${esc(p.name)}</strong>` : `<a class="problem-name" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.name)}</a>`}<div class="problem-tags">${p.tags.map((t) => esc(t)).join(", ")}</div><p class="problem-reason">${esc(p.reason)}${data.sample ? " Sample exercise; no live link." : ""}</p></td><td class="problem-rating">${p.rating}</td><td class="problem-chance">${Math.round(p.probability * 100)}%<small>${esc(p.role)}</small></td></tr>`,
      )
      .join("") ||
      '<tr><td colspan="4">No matching unseen problems. More practice will refine your estimates.</td></tr>') +
    "</tbody></table>";
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
  if (version !== loadVersion) return;
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
  if (version !== loadVersion) return;
  await metrics();
  if (version !== loadVersion) return;
  view(activeView);
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
  if (!m.available) {
    $("model-metrics").textContent =
      "No trained classifier yet. Recommendations use Elo estimates.";
    return;
  }
  const result = m.metrics;
  const percent = (value) =>
    value == null ? "Not available" : `${(value * 100).toFixed(1)}%`;
  const score = (value) => (value == null ? "Not available" : value.toFixed(3));
  const band = result.recommendation_band;
  $("model-metrics").innerHTML =
    `<p>${m.profiles ? `${m.profiles} real profiles · ` : ""}${result.training_attempts} training attempts · ${result.test_attempts} later test attempts.</p><table class="problems-table"><thead><tr><th>Model</th><th>Accuracy</th><th>Brier score ↓</th></tr></thead><tbody><tr><td>Logistic regression</td><td>${percent(result.accuracy)}</td><td>${score(result.brier)}</td></tr><tr><td>Constant training base rate</td><td>${percent(result.majority_accuracy)}</td><td>${score(result.base_rate_brier)}</td></tr><tr><td>Elo estimates</td><td>Not evaluated</td><td>${score(result.elo_brier)}</td></tr></tbody></table><p>Log loss: ${score(result.log_loss)}. Accuracy is affected by the proportion of successful attempts.</p>${band ? `<p>50–70% band: ${band.count} test attempts; predicted ${percent(band.mean_predicted)}, observed ${percent(band.observed_success)}.</p>` : ""}`;
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
let problemPage = 1,
  problemPages = 1,
  problemVersion = 0,
  gymVersion = 0;
let filterSetup;
$("refresh-catalog").onclick = () =>
  guarded(async () => {
    $("refresh-catalog").disabled = true;
    try {
      status("Refreshing the Codeforces catalog…");
      await api("/problems/refresh", { method: "POST" });
      status("Catalog refreshed.");
      await loadProblems(1);
    } finally {
      $("refresh-catalog").disabled = false;
    }
  });
function practiceFilters() {
  if (!filterSetup)
    filterSetup = Promise.all([api("/practice/topics"), api("/topics")])
      .then(([groups, tags]) => {
        $("problem-category").innerHTML =
          '<option value="">All topics</option>' +
          groups
            .map((g) => `<option value="${esc(g.id)}">${esc(g.name)}</option>`)
            .join("");
        $("problem-tag").innerHTML =
          '<option value="">All tags</option>' +
          tags.map((tag) => `<option>${esc(tag)}</option>`).join("");
      })
      .catch((error) => {
        filterSetup = null;
        throw error;
      });
  return filterSetup;
}
function practiceTable(items, start = 0, showRoles = false) {
  return (
    '<table class="problems-table"><thead><tr><th scope="col">#</th><th scope="col">Problem</th><th scope="col">Rating</th><th scope="col">' +
    (showRoles ? "Practice role" : "Status") +
    "</th></tr></thead><tbody>" +
    (items
      .map(
        (p, i) =>
          `<tr class="${p.status === "solved" ? "solved-row" : ""}"><td>${showRoles ? i + 1 : start + i + 1}</td><td>${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.contestId + p.index)} · ${esc(p.name)}</a>` : `<strong>${esc(p.name)} (sample)</strong>`}<div class="problem-tags">${p.tags.map(esc).join(", ")}</div>${p.reason ? `<p class="problem-reason">${esc(p.reason)}</p>` : ""}</td><td class="problem-rating">${p.rating ?? "Unrated"}</td><td>${showRoles ? `${esc(p.role)}<br><small>${Math.round(p.probability * 100)}% Elo heuristic</small>` : esc(p.status)}</td></tr>`,
      )
      .join("") ||
      '<tr><td colspan="4">No matching problems. Adjust the filters or synchronize a profile to populate the catalog.</td></tr>') +
    "</tbody></table>"
  );
}
async function loadProblems(page = 1) {
  const version = ++problemVersion,
    owner = handle;
  await practiceFilters();
  const query = new URLSearchParams({
    search: $("problem-search").value.trim(),
    category: $("problem-category").value,
    tag: $("problem-tag").value,
    minimum: $("problem-min").value,
    maximum: $("problem-max").value,
    state: $("problem-state").value,
    sort: $("problem-sort").value,
    include_unrated: String($("problem-unrated").checked),
    page: String(page),
  });
  if (owner) query.set("handle", owner);
  $("problem-summary").textContent = "Loading catalog…";
  let result;
  try {
    result = await api("/problems?" + query);
  } catch (error) {
    if (version === problemVersion && owner === handle) {
      $("problem-summary").textContent = error.message;
      $("problem-table").innerHTML = "";
      $("problem-prev").disabled = true;
      $("problem-next").disabled = true;
    }
    throw error;
  }
  if (version !== problemVersion || owner !== handle) return;
  problemPage = result.page;
  problemPages = result.pages;
  $("problem-summary").textContent =
    `${result.total} matching problems${result.sample ? " · Synthetic sample catalog" : ""}${owner ? " · Status for " + owner : ""}.`;
  $("problem-table").innerHTML = practiceTable(
    result.items,
    (page - 1) * result.page_size,
  );
  $("problem-page").textContent = `Page ${page} of ${result.pages}`;
  $("problem-prev").disabled = page <= 1;
  $("problem-next").disabled = page >= result.pages;
}
$("problem-filter").onsubmit = (e) => {
  e.preventDefault();
  guarded(() => loadProblems(1));
};
$("problem-prev").onclick = () =>
  guarded(() => loadProblems(Math.max(1, problemPage - 1)));
$("problem-next").onclick = () =>
  guarded(() => loadProblems(Math.min(problemPages, problemPage + 1)));
async function loadGym() {
  const version = ++gymVersion,
    owner = handle;
  if (!owner) {
    $("gym-summary").textContent =
      "Select or connect a profile to personalize your topic gym.";
    $("gym-topics").innerHTML = "";
    return;
  }
  $("gym-summary").textContent = "Building topic practice sets…";
  $("gym-topics").innerHTML = "";
  let result;
  try {
    result = await api(`/profiles/${encodeURIComponent(owner)}/gym`);
  } catch (error) {
    if (version === gymVersion && owner === handle)
      $("gym-summary").textContent = error.message;
    throw error;
  }
  if (version !== gymVersion || owner !== handle) return;
  $("gym-summary").textContent =
    `Training for ${owner}, using rating reference ${result.rating_reference}${result.provisional_rating ? " (provisional: no official rating)" : ""}. Warm-up at or below your rounded rating; main +100; stretch +200. Each topic has its own set, so problems can appear in more than one topic.`;
  $("gym-topics").innerHTML = result.topics
    .map(
      (topic, i) =>
        `<details class="topic-gym" ${i === 0 ? "open" : ""}><summary>${esc(topic.name)} <span>${topic.solved} solved / ${topic.catalog_problems} catalog problems</span></summary><div class="gym-content"><p>${topic.attempted_unsolved} attempted but unsolved · Tags: ${topic.tags.map(esc).join(", ")}</p><p><a href="${esc(topic.resource)}" target="_blank" rel="noopener">Learning resource ↗</a> · <button class="text-button" data-browse-topic="${esc(topic.id)}">Browse all ${esc(topic.name.toLowerCase())} problems</button></p>${topic.recommendations.length ? practiceTable(topic.recommendations, 0, true) : "<p>No unseen problems fit the current difficulty and estimate rules. Browse the topic manually; the gym will not silently recommend harder problems.</p>"}</div></details>`,
    )
    .join("");
  for (const button of document.querySelectorAll("[data-browse-topic]"))
    button.onclick = () =>
      guarded(async () => {
        await practiceFilters();
        $("problem-category").value = button.dataset.browseTopic;
        $("problem-tag").value = "";
        $("problem-search").value = "";
        $("problem-state").value = "unattempted";
        $("problem-min").value = "800";
        $("problem-max").value = "4000";
        view("problemset");
      });
}
view(activeView);
guarded(async () => {
  await savedProfiles();
  const saved = localStorage.getItem("upsolve.handle");
  if (saved) await load(saved);
});
