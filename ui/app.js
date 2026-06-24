// ── Auth ──────────────────────────────────────────────────────────────────────

function getAdminKey() {
  return document.getElementById("adminKey").value.trim();
}

function setAuthStatus(ok) {
  const el = document.getElementById("authStatus");
  el.textContent = ok ? "set" : "not set";
  el.className = ok ? "badge badge-green" : "badge badge-muted";
}

(function initAuth() {
  const saved = localStorage.getItem("redline_admin_key");
  if (saved) {
    document.getElementById("adminKey").value = saved;
    setAuthStatus(true);
  }
})();

document.getElementById("adminKey").addEventListener("input", () => {
  setAuthStatus(!!document.getElementById("adminKey").value.trim());
});

document.getElementById("saveKey").addEventListener("click", () => {
  const key = getAdminKey();
  if (key) {
    localStorage.setItem("redline_admin_key", key);
    setAuthStatus(true);
  }
});

// ── Slider ────────────────────────────────────────────────────────────────────

const slider = document.getElementById("testcaseCount");
const sliderLabel = document.getElementById("testcaseCountLabel");
slider.addEventListener("input", () => { sliderLabel.textContent = slider.value; });

// ── API helper ────────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const adminKey = getAdminKey();
  if (!adminKey) throw new Error("Admin key is required — enter it above and click Save.");
  const headers = { "X-Admin-Key": adminKey, ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  const resp = await fetch(path, { ...options, headers });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || resp.statusText);
  return data;
}

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

function renderResults(data) {
  const summary   = data.summary || {};
  const passRate  = summary.pass_rate ?? 0;
  const pct       = Math.round(passRate * 100);
  const tier      = data.tier || "At Risk";
  const cfg       = TIER_CONFIG[tier] || TIER_CONFIG["At Risk"];

  document.getElementById("resultsSection").classList.remove("hidden");

  // Tier card
  document.getElementById("tierEmoji").textContent = cfg.emoji;

  const tierLabel = document.getElementById("tierLabel");
  tierLabel.textContent = tier;
  tierLabel.className = `tier-label ${cfg.cls}`;

  const passRateNum = document.getElementById("passRateNumber");
  passRateNum.textContent = `${pct}%`;
  passRateNum.className = `pass-rate-number ${cfg.cls}`;

  document.getElementById("mainProgressBar").style.cssText =
    `width: ${pct}%; background: ${cfg.barColor}`;

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
      const bad = Object.entries(r.scores || {})
        .filter(([, v]) => v === false)
        .map(([k]) => k)
        .join(", ");
      return `<div class="failure-item">
        <div class="failure-id">${r.testcase_id}</div>
        <div class="failure-metrics">Failed: ${bad || "unknown"}</div>
      </div>`;
    }).join("");

    if (failures.length > 8) {
      list.innerHTML += `<p class="hint" style="margin-top:8px">…and ${failures.length - 8} more</p>`;
    }
  }

  // Run metadata
  document.getElementById("runMeta").textContent =
    `run_id: ${data.run_id}  ·  project_id: ${data.project_id}  ·  model: ${data.model || "default"}  ·  mode: ${data.mode}`;
}

// ── Agent endpoint toggle ─────────────────────────────────────────────────────

document.getElementById("useCustomAgent").addEventListener("change", (e) => {
  const fields = document.getElementById("agentEndpointFields");
  fields.classList.toggle("hidden", !e.target.checked);
});

// ── Quick Eval ────────────────────────────────────────────────────────────────

document.getElementById("runQuickEval").addEventListener("click", async () => {
  const btn             = document.getElementById("runQuickEval");
  const progressSection = document.getElementById("progressSection");
  const progressBar     = document.getElementById("progressBar");
  const progressLabel   = document.getElementById("progressLabel");
  const resultsSection  = document.getElementById("resultsSection");
  const failuresCard    = document.getElementById("failuresCard");

  const setProgress = (pct, label) => {
    progressBar.style.width = `${pct}%`;
    progressLabel.textContent = label;
  };

  try {
    btn.disabled = true;
    btn.textContent = "Running…";
    progressSection.classList.remove("hidden");
    resultsSection.classList.add("hidden");
    failuresCard.classList.add("hidden");
    progressBar.style.background = "var(--accent)";

    setProgress(5, "Queuing run…");

    const count       = parseInt(document.getElementById("testcaseCount").value, 10);
    const mode        = document.getElementById("runMode").value;
    const model       = document.getElementById("runModel").value.trim() || undefined;
    const useCustom   = document.getElementById("useCustomAgent").checked;
    const endpointUrl = useCustom ? document.getElementById("agentEndpointUrl").value.trim() : undefined;
    const endpointKey = useCustom ? document.getElementById("agentEndpointKey").value.trim() : undefined;

    if (useCustom && !endpointUrl) {
      throw new Error("Agent endpoint URL is required when 'Test my own agent' is checked.");
    }

    const queued = await apiFetch("/quick-eval", {
      method: "POST",
      body: JSON.stringify({
        testcase_count: count,
        mode,
        ...(model && { model }),
        ...(endpointUrl && { agent_endpoint_url: endpointUrl }),
        ...(endpointKey && { agent_endpoint_key: endpointKey }),
      }),
    });

    const { run_id, project_id, testcase_count } = queued;
    setProgress(15, `Run queued — ${testcase_count} test cases loading…`);

    // Stream live status
    const adminKey = getAdminKey();
    const finalStatus = await new Promise((resolve) => {
      const url = `/projects/${project_id}/runs/${run_id}/stream?x_admin_key=${encodeURIComponent(adminKey)}`;
      const es = new EventSource(url);
      es.onmessage = (e) => {
        const payload = JSON.parse(e.data);
        if (payload.status === "running") setProgress(55, "Evaluating test cases…");
        if (payload.status === "completed" || payload.status === "failed") {
          es.close();
          resolve(payload.status);
        }
      };
      es.onerror = () => { es.close(); resolve("error"); };
      setTimeout(() => { es.close(); resolve("timeout"); }, 180_000);
    });

    if (finalStatus !== "completed") {
      progressBar.style.background = "#ef4444";
      setProgress(100, finalStatus === "timeout"
        ? "Timed out — run may still be in progress."
        : "Run failed. Check your API key and model config.");
      return;
    }

    setProgress(88, "Fetching results…");
    const final = await apiFetch(`/quick-eval/${run_id}`);
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
      method: "POST",
      body: JSON.stringify({ testcase_ids: ids, mode, llm_model: llm, seed }),
    });
    document.getElementById("runId").value = data.run_id;
    rawOutput(data);
  } catch (err) { rawOutput(String(err)); }
});

document.getElementById("getRun").addEventListener("click", async () => {
  try {
    const pid = document.getElementById("projectId").value.trim();
    const rid = document.getElementById("runId").value.trim();
    rawOutput(await apiFetch(`/projects/${pid}/runs/${rid}`));
  } catch (err) { rawOutput(String(err)); }
});

document.getElementById("getResults").addEventListener("click", async () => {
  try {
    const pid = document.getElementById("projectId").value.trim();
    const rid = document.getElementById("runId").value.trim();
    rawOutput(await apiFetch(`/projects/${pid}/runs/${rid}/results`));
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
