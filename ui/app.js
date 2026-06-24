// ── HTML escaping (XSS prevention) ───────────────────────────────────────────

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── Admin toggle ──────────────────────────────────────────────────────────────

function toggleAdmin() {
  const s = document.getElementById("adminSection");
  s.classList.toggle("visible");
}

function getAdminKey() {
  const el = document.getElementById("adminKey");
  return el ? el.value.trim() : "";
}

function setAuthStatus(ok) {
  const el = document.getElementById("authStatus");
  if (!el) return;
  el.textContent = ok ? "set" : "not set";
  el.className = ok ? "badge badge-green" : "badge badge-muted";
}

(function initAuth() {
  const saved = localStorage.getItem("redline_admin_key");
  if (saved) {
    const el = document.getElementById("adminKey");
    if (el) el.value = saved;
    setAuthStatus(true);
  }
})();

document.getElementById("adminKey")?.addEventListener("input", () => {
  setAuthStatus(!!getAdminKey());
});

document.getElementById("saveKey")?.addEventListener("click", () => {
  const key = getAdminKey();
  if (key) { localStorage.setItem("redline_admin_key", key); setAuthStatus(true); }
});

// ── Slider ────────────────────────────────────────────────────────────────────

const slider = document.getElementById("testcaseCount");
const sliderLabel = document.getElementById("testcaseCountLabel");
slider.addEventListener("input", () => { sliderLabel.textContent = slider.value; });

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const adminKey = getAdminKey();
  const headers = { ...(options.headers || {}) };
  if (adminKey) headers["X-Admin-Key"] = adminKey;
  if (options.body) headers["Content-Type"] = "application/json";
  const resp = await fetch(path, { ...options, headers });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || resp.statusText);
  return data;
}

async function publicFetch(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(resp.statusText);
  return resp.json();
}

// ── Leaderboard ───────────────────────────────────────────────────────────────

async function loadLeaderboard() {
  try {
    const { entries, total_runs, total_models, avg_pass_pct } = await publicFetch("/leaderboard");

    // Stats bar
    document.getElementById("statRuns").textContent   = total_runs ?? "—";
    document.getElementById("statModels").textContent = total_models ?? "—";
    document.getElementById("statAvg").textContent    = avg_pass_pct != null ? `${avg_pass_pct}%` : "—";

    const tbody = document.getElementById("lbBody");
    if (!entries || entries.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="lb-empty">No evals yet — be the first to run one below 👇</td></tr>`;
      return;
    }

    const myName = localStorage.getItem("redline_submitter") || "";
    tbody.innerHTML = entries.map(e => {
      const isYou = myName && e.submitter === myName;
      return `<tr class="${isYou ? "lb-you" : ""}">
        <td class="lb-rank">${esc(e.rank)}</td>
        <td>
          <div class="lb-model">${esc(e.model)}${isYou ? " 👈 you" : ""}</div>
          <div class="lb-sub">by ${esc(e.submitter || "anonymous")}</div>
        </td>
        <td class="lb-pct">${esc(e.pass_pct)}%</td>
        <td><span class="lb-tier">${esc(e.tier || "—")}</span></td>
        <td class="lb-date">${esc(e.testcase_count ?? "—")}</td>
        <td class="lb-date">${esc(e.date || "—")}</td>
      </tr>`;
    }).join("");
  } catch (e) {
    document.getElementById("lbBody").innerHTML = `<tr><td colspan="6" class="lb-empty">Could not load leaderboard.</td></tr>`;
  }
}

loadLeaderboard();

// ── Render helpers ────────────────────────────────────────────────────────────

const TIER_CONFIG = {
  "Hardened":   { emoji: "💎", cls: "tier-hardened",   barColor: "#3ddc97" },
  "Safe":       { emoji: "✅", cls: "tier-safe",        barColor: "#22c55e" },
  "Developing": { emoji: "🟡", cls: "tier-developing",  barColor: "#eab308" },
  "At Risk":    { emoji: "🔴", cls: "tier-at-risk",     barColor: "#ef4444" },
};

const METRIC_LABELS = {
  policy_compliance: "Policy compliance",
  hallucination:     "Hallucination avoidance",
  must_include:      "Must-include phrases",
  must_not_include:  "Must-not-include phrases",
  strongreject:      "StrongREJECT — no specific harmful content",
  overconfidence:    "Overconfidence avoidance",
};

function metricColor(pct) {
  if (pct >= 75) return "#22c55e";
  if (pct >= 60) return "#eab308";
  return "#ef4444";
}

let _lastResult = null;

function renderResults(data) {
  _lastResult = data;
  const summary  = data.summary || {};
  const passRate = summary.pass_rate ?? 0;
  const pct      = Math.round(passRate * 100);
  const tier     = data.tier || "At Risk";
  const cfg      = TIER_CONFIG[tier] || TIER_CONFIG["At Risk"];

  document.getElementById("resultsSection").classList.remove("hidden");

  document.getElementById("tierEmoji").textContent = cfg.emoji;

  const tierLabel = document.getElementById("tierLabel");
  tierLabel.textContent = tier;
  tierLabel.className = `tier-label ${cfg.cls}`;

  const passRateNum = document.getElementById("passRateNumber");
  passRateNum.textContent = `${pct}%`;
  passRateNum.className = `pass-rate-number ${cfg.cls}`;

  document.getElementById("mainProgressBar").style.cssText = `width:${pct}%;background:${cfg.barColor}`;

  // Metrics
  const metrics = summary.metrics || {};
  const grid = document.getElementById("metricsGrid");
  grid.innerHTML = "";
  for (const [key, label] of Object.entries(METRIC_LABELS)) {
    const m = metrics[key];
    if (!m) continue;
    const mpct  = Math.round((m.pass_rate ?? 0) * 100);
    const icon  = mpct >= 75 ? "✅" : (mpct >= 60 ? "⚠️" : "❌");
    const color = metricColor(mpct);
    grid.innerHTML += `
      <div class="metric-row">
        <span class="metric-icon">${icon}</span>
        <span class="metric-name">${label}</span>
        <span class="metric-pct" style="color:${color}">${mpct}%</span>
      </div>
      <div class="metric-bar-wrap">
        <div class="metric-bar-fill" style="width:${mpct}%;background:${color}"></div>
      </div>`;
  }

  // Failures
  const results  = data.results || [];
  const failures = results.filter(r => !r.passed);
  if (failures.length > 0) {
    document.getElementById("failuresCard").classList.remove("hidden");
    document.getElementById("failureCount").textContent = String(failures.length);
    const list = document.getElementById("failuresList");
    list.innerHTML = failures.slice(0, 8).map(r => {
      const bad = Object.entries(r.scores || {}).filter(([, v]) => v === false).map(([k]) => esc(k)).join(", ");
      return `<div class="failure-item"><div class="failure-id">${esc(r.testcase_id)}</div><div class="failure-metrics">Failed: ${bad || "unknown"}</div></div>`;
    }).join("");
    if (failures.length > 8) list.innerHTML += `<p class="hint" style="margin-top:8px">…and ${failures.length - 8} more</p>`;
  }

  document.getElementById("runMeta").textContent =
    `run_id: ${data.run_id}  ·  project_id: ${data.project_id}  ·  model: ${data.model || "default"}  ·  mode: ${data.mode}`;

  // Reload leaderboard to show new rank
  loadLeaderboard().then(() => {
    const myName = localStorage.getItem("redline_submitter") || "";
    const rows = document.querySelectorAll("#lbBody tr.lb-you");
    if (rows.length > 0) {
      const rankCell = rows[0].querySelector(".lb-rank");
      if (rankCell) {
        document.getElementById("yourRank").textContent = `🏆 You're ranked #${rankCell.textContent} on the leaderboard`;
      }
    }
  });
}

// ── Share ─────────────────────────────────────────────────────────────────────

function shareResult() {
  if (!_lastResult) return;
  const pct   = Math.round((_lastResult.summary?.pass_rate ?? 0) * 100);
  const tier  = _lastResult.tier || "At Risk";
  const model = _lastResult.model || "my model";
  const text  = `I just tested ${model} on Redline safety evals and scored ${pct}% (${tier})! Test your agent: https://redline-safety.fly.dev`;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => alert("Copied to clipboard! Share it anywhere."));
  } else {
    prompt("Copy this:", text);
  }
}

function scrollToRun() {
  document.getElementById("runSection").scrollIntoView({ behavior: "smooth" });
}

// ── Agent endpoint toggle ─────────────────────────────────────────────────────

document.getElementById("useCustomAgent").addEventListener("change", (e) => {
  document.getElementById("agentEndpointFields").classList.toggle("hidden", !e.target.checked);
});

// ── Quick Eval ────────────────────────────────────────────────────────────────

document.getElementById("runQuickEval").addEventListener("click", async () => {
  const btn             = document.getElementById("runQuickEval");
  const progressSection = document.getElementById("progressSection");
  const progressBar     = document.getElementById("progressBar");
  const progressLabel   = document.getElementById("progressLabel");
  const failuresCard    = document.getElementById("failuresCard");

  const setProgress = (pct, label) => {
    progressBar.style.width = `${pct}%`;
    progressLabel.textContent = label;
  };

  try {
    btn.disabled = true;
    btn.textContent = "Running…";
    progressSection.classList.remove("hidden");
    document.getElementById("resultsSection").classList.add("hidden");
    failuresCard.classList.add("hidden");
    progressBar.style.background = "var(--accent)";

    setProgress(5, "Queuing run…");

    const count       = parseInt(document.getElementById("testcaseCount").value, 10);
    const mode        = document.getElementById("runMode").value;
    const model       = document.getElementById("runModel").value.trim() || undefined;
    const submitter   = document.getElementById("submitterName").value.trim() || undefined;
    const useCustom   = document.getElementById("useCustomAgent").checked;
    const endpointUrl = useCustom ? document.getElementById("agentEndpointUrl").value.trim() : undefined;
    const endpointKey = useCustom ? document.getElementById("agentEndpointKey").value.trim() : undefined;

    if (useCustom && !endpointUrl) throw new Error("Agent endpoint URL is required.");
    if (submitter) localStorage.setItem("redline_submitter", submitter);

    const queued = await fetch("/quick-eval", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        testcase_count: count, mode,
        ...(model       && { model }),
        ...(submitter   && { submitter }),
        ...(endpointUrl && { agent_endpoint_url: endpointUrl }),
        ...(endpointKey && { agent_endpoint_key: endpointKey }),
      }),
    }).then(r => r.json());

    if (!queued.run_id) throw new Error(queued.detail || "Failed to queue run.");

    const { run_id, project_id, testcase_count } = queued;
    setProgress(15, `Queued — ${testcase_count} test cases loading…`);

    // SSE stream — use admin key if set, otherwise stream_url from server
    const adminKey  = getAdminKey();
    const streamUrl = queued.stream_url || `/projects/${project_id}/runs/${run_id}/stream?x_admin_key=${encodeURIComponent(adminKey)}`;

    const finalStatus = await new Promise((resolve) => {
      const es = new EventSource(streamUrl);
      es.onmessage = (e) => {
        const payload = JSON.parse(e.data);
        if (payload.status === "running") setProgress(55, "Evaluating test cases — this takes ~2 min for 10 cases…");
        if (payload.status === "completed" || payload.status === "failed") { es.close(); resolve(payload.status); }
      };
      es.onerror = () => { es.close(); resolve("error"); };
      setTimeout(() => { es.close(); resolve("timeout"); }, 300_000);
    });

    if (finalStatus !== "completed") {
      progressBar.style.background = "#ef4444";
      setProgress(100, finalStatus === "timeout" ? "Timed out — run may still be processing." : "Run failed. Check model config.");
      return;
    }

    setProgress(88, "Fetching results…");
    const final = await fetch(`/quick-eval/${run_id}`, {
      headers: adminKey ? { "X-Admin-Key": adminKey } : {},
    }).then(r => r.json());
    setProgress(100, "Done.");
    renderResults(final);

  } catch (err) {
    progressBar.style.background = "#ef4444";
    document.getElementById("progressLabel").textContent = `Error: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ Run Safety Eval";
  }
});

// ── Advanced handlers ─────────────────────────────────────────────────────────

function rawOutput(value) {
  document.getElementById("output").textContent =
    typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

document.getElementById("createProject").addEventListener("click", async () => {
  try {
    let name = document.getElementById("projectName").value.trim();
    if (!name) { name = `project-${Date.now()}`; document.getElementById("projectName").value = name; }
    const data = await apiFetch("/projects", { method: "POST", body: JSON.stringify({ name }) });
    document.getElementById("projectId").value = data.id;
    rawOutput(data);
  } catch (err) { rawOutput(String(err)); }
});

document.getElementById("seedTestcases").addEventListener("click", async () => {
  try {
    const pid = document.getElementById("projectId").value.trim();
    if (!pid) throw new Error("Project ID required");
    rawOutput(await apiFetch(`/projects/${pid}/seed-testcases`, { method: "POST" }));
  } catch (err) { rawOutput(String(err)); }
});

document.getElementById("listTestcases").addEventListener("click", async () => {
  try {
    const pid = document.getElementById("projectId").value.trim();
    if (!pid) throw new Error("Project ID required");
    const data = await apiFetch(`/projects/${pid}/testcases`);
    document.getElementById("testcaseIds").value = data.map(t => t.id).join(", ");
    rawOutput(data);
  } catch (err) { rawOutput(String(err)); }
});

document.getElementById("createRun").addEventListener("click", async () => {
  try {
    const pid  = document.getElementById("projectId").value.trim();
    if (!pid) throw new Error("Project ID required");
    const ids  = document.getElementById("testcaseIds").value.split(",").map(s => s.trim()).filter(Boolean);
    const mode = document.getElementById("advRunMode").value;
    const llm  = document.getElementById("advRunModel").value.trim() || null;
    const seed = Number(document.getElementById("advRunSeed").value || 0);
    const data = await apiFetch(`/projects/${pid}/runs`, {
      method: "POST", body: JSON.stringify({ testcase_ids: ids, mode, llm_model: llm, seed }),
    });
    document.getElementById("runId").value = data.run_id;
    rawOutput(data);
  } catch (err) { rawOutput(String(err)); }
});

document.getElementById("getRun").addEventListener("click", async () => {
  try {
    rawOutput(await apiFetch(`/projects/${document.getElementById("projectId").value.trim()}/runs/${document.getElementById("runId").value.trim()}`));
  } catch (err) { rawOutput(String(err)); }
});

document.getElementById("getResults").addEventListener("click", async () => {
  try {
    rawOutput(await apiFetch(`/projects/${document.getElementById("projectId").value.trim()}/runs/${document.getElementById("runId").value.trim()}/results`));
  } catch (err) { rawOutput(String(err)); }
});

document.getElementById("getTrace").addEventListener("click", async () => {
  try {
    const pid = document.getElementById("projectId").value.trim();
    const rid = document.getElementById("runId").value.trim();
    const tid = document.getElementById("traceTestcaseId").value.trim();
    rawOutput(await apiFetch(`/projects/${pid}/runs/${rid}/traces/${tid}`));
  } catch (err) { rawOutput(String(err)); }
});
