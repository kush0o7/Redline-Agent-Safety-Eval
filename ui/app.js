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

// ── Deployment info (demo banner, auth hint) ─────────────────────────────────

(async function initDeployment() {
  try {
    const info = await publicFetch("/health");
    if (info.deployment === "demo") {
      document.getElementById("demoBanner")?.classList.remove("hidden");
    }
    if (info.eval_auth_required && !getAdminKey()) {
      document.getElementById("adminSection")?.classList.add("visible");
    }
  } catch (e) { /* health unavailable — leave defaults */ }
})();

// ── Render helpers ────────────────────────────────────────────────────────────

const TIER_CONFIG = {
  "Hardened":   { emoji: "💎", cls: "tier-hardened",   barColor: "#3ddc97" },
  "Safe":       { emoji: "✅", cls: "tier-safe",        barColor: "#22c55e" },
  "Developing": { emoji: "🟡", cls: "tier-developing",  barColor: "#eab308" },
  "At Risk":    { emoji: "🔴", cls: "tier-at-risk",     barColor: "#ef4444" },
  "Provisional":{ emoji: "⏳", cls: "tier-provisional", barColor: "#64748b" },
};

const METRIC_LABELS = {
  policy_compliance: "Policy compliance",
  hallucination:     "Hallucination avoidance",
  must_include:      "Must-include phrases",
  must_not_include:  "Must-not-include phrases",
  strongreject:      "StrongREJECT — no specific harmful content",
  overconfidence:    "Overconfidence avoidance",
  injection_resisted: "Injection resisted (graded in code)",
};

const DECIDED_BY_LABELS = {
  code:      "Checked in code (agent actions)",
  judge:     "LLM judge",
  heuristic: "Keyword heuristic (test mode)",
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

  // Confidence interval
  const ci = summary.confidence_interval;
  const ciEl = document.getElementById("confidenceInterval");
  if (ciEl && ci) {
    const ciLo = Math.round(ci.low * 100);
    const ciHi = Math.round(ci.high * 100);
    ciEl.textContent = `95% CI: ${ciLo}–${ciHi}% (n=${ci.n})`;
    ciEl.title = "Wilson score confidence interval. Run 50+ cases for tighter bounds.";
  }
  if (summary.sample_size_warning) {
    const warn = document.getElementById("sampleWarn");
    if (warn) warn.classList.remove("hidden");
  }

  // Tier explanation: provisional status + why higher tiers were missed
  const tierEval = data.tier_evaluation || summary.tier_evaluation || null;
  const reasonsEl = document.getElementById("tierReasons");
  if (reasonsEl) {
    const reasons = (tierEval && tierEval.reasons) || [];
    const lines = [];
    if (tierEval && tierEval.provisional) lines.push(`Indicative tier: ${tierEval.indicative_tier}`);
    lines.push(...reasons);
    reasonsEl.innerHTML = lines.map(r => `<li>${esc(r)}</li>`).join("");
  }

  // Per-category breakdowns: scoring categories (what tiers are judged on) and raw test types
  renderBreakdown("categoryCard", "categoryGrid", summary.tier_categories || {});
  renderBreakdown("typeCard", "typeGrid", summary.categories || {});

  // Metric breakdown
  const metrics = summary.metrics || {};
  const grid = document.getElementById("metricsGrid");
  grid.innerHTML = "";
  for (const [key, label] of Object.entries(METRIC_LABELS)) {
    const m = metrics[key];
    if (!m) continue;
    const mpct  = Math.round((m.pass_rate ?? 0) * 100);
    const icon  = mpct >= 75 ? "✅" : (mpct >= 60 ? "⚠️" : "❌");
    const color = metricColor(mpct);
    const ciStr = m.ci_low != null ? ` <span style="color:var(--muted);font-size:11px">${Math.round(m.ci_low*100)}–${Math.round(m.ci_high*100)}%</span>` : "";
    grid.innerHTML += `
      <div class="metric-row">
        <span class="metric-icon">${icon}</span>
        <span class="metric-name">${label}</span>
        <span class="metric-pct" style="color:${color}">${mpct}%${ciStr}</span>
      </div>
      <div class="metric-bar-wrap">
        <div class="metric-bar-fill" style="width:${mpct}%;background:${color}"></div>
      </div>`;
  }

  // Failures — full detail with prompt, response, judge reasoning
  const results  = data.results || [];
  const failures = results.filter(r => !r.passed);
  if (failures.length > 0) {
    document.getElementById("failuresCard").classList.remove("hidden");
    document.getElementById("failureCount").textContent = String(failures.length);
    const list = document.getElementById("failuresList");
    list.innerHTML = failures.map(r => {
      const bad = Object.entries(r.scores || {}).filter(([, v]) => v === false).map(([k]) => esc(METRIC_LABELS[k] || k)).join(", ");
      const jr = r.judge_reasoning || {};
      const reasoning = jr.refusal_reasoning || jr.hallucination_reasoning || jr.reasoning || "";
      const decidedBy = r.decided_by || jr.decided_by;
      const evidence = Array.isArray(jr.evidence) ? jr.evidence : [];
      return `<details class="failure-item">
        <summary>
          <span class="failure-type">${esc(r.testcase_type || "unknown")}</span>
          <span class="failure-name">${esc(r.testcase_name || r.testcase_id)}</span>
          <span class="failure-metrics">Failed: ${bad || "unknown"}</span>
        </summary>
        <div class="failure-detail">
          <div class="detail-block">
            <div class="detail-label">Prompt</div>
            <div class="detail-text">${esc(r.prompt || "")}</div>
          </div>
          <div class="detail-block">
            <div class="detail-label">Model response</div>
            <div class="detail-text">${esc(r.response || "")}</div>
          </div>
          ${jr.attack_goal ? `<div class="detail-block">
            <div class="detail-label">Attacker's goal</div>
            <div class="detail-text">${esc(jr.attack_goal)}</div>
          </div>` : ""}
          ${evidence.length ? `<div class="detail-block">
            <div class="detail-label">Evidence</div>
            <div class="detail-text">${evidence.map(e => esc(e)).join("<br>")}</div>
          </div>` : ""}
          ${decidedBy ? `<div class="detail-block">
            <div class="detail-label">Decided by</div>
            <div class="detail-text">${esc(DECIDED_BY_LABELS[decidedBy] || decidedBy)}</div>
          </div>` : ""}
          ${reasoning ? `<div class="detail-block">
            <div class="detail-label">Judge reasoning</div>
            <div class="detail-text detail-reasoning">${esc(reasoning)}</div>
          </div>` : ""}
        </div>
      </details>`;
    }).join("");
  }

  document.getElementById("runMeta").textContent =
    `run_id: ${data.run_id}  ·  project_id: ${data.project_id}  ·  model: ${data.model || "default"}  ·  mode: ${data.mode}`;
}

function renderBreakdown(cardId, gridId, groups) {
  const grid = document.getElementById(gridId);
  if (!grid || Object.keys(groups).length === 0) return;
  document.getElementById(cardId)?.style.setProperty("display", "block");
  grid.innerHTML = Object.entries(groups).sort((a,b)=>a[0].localeCompare(b[0])).map(([name, c]) => {
    const cpct = Math.round((c.pass_rate ?? 0) * 100);
    const color = metricColor(cpct);
    return `<div class="metric-row">
      <span class="metric-icon">${cpct >= 75 ? "✅" : cpct >= 60 ? "⚠️" : "❌"}</span>
      <span class="metric-name">${esc(name)} <span style="color:var(--muted);font-size:11px">(${esc(c.pass)}/${esc(c.total)})</span></span>
      <span class="metric-pct" style="color:${color}">${cpct}%</span>
    </div>
    <div class="metric-bar-wrap"><div class="metric-bar-fill" style="width:${cpct}%;background:${color}"></div></div>`;
  }).join("");
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

    const rerunOf     = document.getElementById("rerunOf").value.trim() || undefined;
    const count       = parseInt(document.getElementById("testcaseCount").value, 10);
    const mode        = document.getElementById("runMode").value;
    const model       = document.getElementById("runModel").value.trim() || undefined;
    const packs       = [...document.querySelectorAll(".pack-box:checked")].map(b => b.value);
    const useCustom   = document.getElementById("useCustomAgent").checked;
    const endpointUrl = useCustom ? document.getElementById("agentEndpointUrl").value.trim() : undefined;
    const endpointKey = useCustom ? document.getElementById("agentEndpointKey").value.trim() : undefined;

    if (useCustom && !endpointUrl) throw new Error("Agent endpoint URL is required.");
    if (packs.length === 0) throw new Error("Select at least one test pack.");

    const authHeaders = getAdminKey() ? { "X-Admin-Key": getAdminKey() } : {};
    const queued = await fetch("/quick-eval", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders },
      body: JSON.stringify({
        mode,
        // rerun_of reuses the earlier run's exact cases, so count and packs don't apply
        ...(rerunOf ? { rerun_of: rerunOf } : { testcase_count: count, packs }),
        ...(model       && { model }),
        ...(endpointUrl && { agent_endpoint_url: endpointUrl }),
        ...(endpointKey && { agent_endpoint_key: endpointKey }),
      }),
    }).then(r => r.json());

    if (!queued.run_id) {
      if (queued.detail === "Unauthorized") throw new Error("This install requires the admin key — open ⚙️ admin and paste ADMIN_API_KEY from your .env.");
      throw new Error(queued.detail || "Failed to queue run.");
    }

    const { run_id, project_id, testcase_count } = queued;
    setProgress(15, `Queued — ${testcase_count} test cases loading…`);

    // Live status: SSE via the per-run stream token; fall back to polling.
    // (Never put the admin key in a URL — query strings end up in logs/history.)
    const adminKey  = getAdminKey();
    const streamUrl = queued.stream_url;

    const watchViaPolling = async () => {
      for (let i = 0; i < 1200; i++) {
        await new Promise(r => setTimeout(r, 3000));
        const data = await fetch(`/quick-eval/${run_id}`, { headers: authHeaders }).then(r => r.json()).catch(() => null);
        if (!data) continue;
        applyProgress(data.status, data.summary);
        if (data.status === "completed" || data.status === "failed") return data.status;
      }
      return "timeout";
    };

    const applyProgress = (status, summary) => {
      if (status !== "running") return;
      const p = summary && summary.progress;
      if (p && p.total) {
        const pct = 20 + Math.round((p.completed / p.total) * 65);
        setProgress(pct, `Evaluating test case ${p.completed}/${p.total}…`);
      } else {
        setProgress(55, "Evaluating test cases…");
      }
    };

    const finalStatus = streamUrl
      ? await new Promise((resolve) => {
          const es = new EventSource(streamUrl);
          es.onmessage = (e) => {
            const payload = JSON.parse(e.data);
            applyProgress(payload.status, payload.summary);
            if (payload.status === "completed" || payload.status === "failed") { es.close(); resolve(payload.status); }
          };
          es.onerror = () => { es.close(); watchViaPolling().then(resolve); };
          setTimeout(() => { es.close(); resolve("timeout"); }, 3_600_000);
        })
      : await watchViaPolling();

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
    // Pre-fill the compare form: this run is the "after"; its rerun source is the "before".
    document.getElementById("compareCandidateId").value = run_id;
    if (final.rerun_of) document.getElementById("compareBaseId").value = final.rerun_of;

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


// ── Compare two runs ──────────────────────────────────────────────────────────

const COMPARE_DECIDED = { code: "code check (agent actions)", judge: "LLM judge", heuristic: "keyword heuristic (test mode)" };

function pctOrDash(v) { return v == null ? "—" : `${Math.round(v * 100)}%`; }
function ptsHtml(d) {
  if (d == null) return "—";
  const pts = Math.round(d * 100);
  const color = pts < 0 ? "#ef4444" : pts > 0 ? "#22c55e" : "var(--muted)";
  return `<span style="color:${color}">${pts > 0 ? "+" : ""}${pts} pts</span>`;
}
function groupCell(g) {
  if (!g) return "—";
  const ci = g.ci_low != null ? ` <span style="color:var(--muted);font-size:11px">${Math.round(g.ci_low*100)}–${Math.round(g.ci_high*100)}%</span>` : "";
  return `${pctOrDash(g.pass_rate)} (${g.pass}/${g.total})${ci}`;
}

// Answers to harmful requests are redacted here, as in the HTML report (full text: report with include_full_outputs).
function compareAnswer(d, text, passed) {
  const t = String(text || "");
  if (!d.should_refuse || passed || /^\[Model [^\]]* — content redacted in simulation\]$/.test(t.trim())) return esc(t);
  const flat = t.split(/\s+/).join(" ");
  return flat.length <= 80 ? "[harmful content — redacted]" : `${esc(flat.slice(0, 80))}… [harmful content — redacted]`;
}

function renderComparison(cmp, baseId, candId) {
  const tc = cmp.tier_change || {};
  const regs = (cmp.flipped || {}).regressions || [];
  const imps = (cmp.flipped || {}).improvements || [];
  document.getElementById("compareSummary").innerHTML = `
    <div><span class="compare-k">Pass rate</span> ${pctOrDash(cmp.base_pass_rate)} → ${pctOrDash(cmp.candidate_pass_rate)} (${ptsHtml(cmp.pass_rate_delta)})</div>
    <div><span class="compare-k">Tier</span> ${esc(tc.from || "—")} → ${esc(tc.to || "—")} ${tc.direction === "down" ? "⬇️" : tc.direction === "up" ? "⬆️" : ""}</div>
    <div><span class="compare-k">Models</span> ${esc((cmp.base || {}).model || "?")} → ${esc((cmp.candidate || {}).model || "?")}</div>
    <div><span class="compare-k">Flipped</span> ${regs.length} regression${regs.length === 1 ? "" : "s"} · ${imps.length} improvement${imps.length === 1 ? "" : "s"} (of ${cmp.common_total} shared cases)</div>
    ${cmp.release ? `<div><span class="compare-k">Release</span> <strong style="color:${cmp.release.decision === "PASS" ? "#22c55e" : "#ef4444"}">${esc(cmp.release.decision)}</strong> — ${esc(cmp.release.reason)}<br><span style="color:var(--muted)">${esc(cmp.release.recommended_action)}</span></div>` : ""}`;
  const warn = document.getElementById("compareWarning");
  const cs = cmp.case_set || {};
  warn.textContent = cs.identical ? "" : `⚠️ ${cs.warning || "These runs did not use identical cases."}`;
  warn.classList.toggle("hidden", !!cs.identical);
  document.getElementById("compareCategories").innerHTML = Object.entries(cmp.categories || {}).map(([name, g]) =>
    `<tr><td>${esc(name)}</td><td>${groupCell(g.base)}</td><td>${groupCell(g.candidate)}</td><td>${ptsHtml(g.delta)}</td></tr>`).join("");
  document.getElementById("compareFlipCount").textContent = String(regs.length);
  document.getElementById("compareFlips").innerHTML = [...regs.map(d => [d, "pass → fail"]), ...imps.map(d => [d, "fail → pass"])].map(([d, dir]) => {
    const evidence = (d.evidence || []).map(e => esc(e)).join("<br>");
    return `<details class="failure-item">
      <summary>
        <span class="failure-type">${esc(d.type || "")}</span>
        <span class="failure-name">${esc(d.name || d.testcase_id)}</span>
        <span class="failure-metrics">${dir} · sev ${esc(d.severity)} · decided by ${esc(COMPARE_DECIDED[d.candidate_decided_by] || d.candidate_decided_by || "—")}</span>
      </summary>
      <div class="failure-detail">
        ${d.attack_goal ? `<div class="detail-block"><div class="detail-label">Attacker's goal</div><div class="detail-text">${esc(d.attack_goal)}</div></div>` : ""}
        <div class="detail-block"><div class="detail-label">Prompt</div><div class="detail-text">${esc(d.prompt || "")}</div></div>
        <div class="detail-block"><div class="detail-label">Before answer (${d.base_passed ? "passed" : "failed"})</div><div class="detail-text">${compareAnswer(d, d.base_answer, d.base_passed)}</div></div>
        <div class="detail-block"><div class="detail-label">After answer (${d.candidate_passed ? "passed" : "failed"})</div><div class="detail-text">${compareAnswer(d, d.candidate_answer, d.candidate_passed)}</div></div>
        ${d.impact ? `<div class="detail-block"><div class="detail-label">Business impact</div><div class="detail-text">${esc(d.impact)}</div></div>` : ""}
        ${evidence ? `<div class="detail-block"><div class="detail-label">Evidence</div><div class="detail-text">${evidence}</div></div>` : ""}
      </div>
    </details>`;
  }).join("") || `<p class="hint">No cases flipped.</p>`;
  document.getElementById("compareReportLink").href =
    `/quick-eval/${encodeURIComponent(candId)}/compare/report?base_run_id=${encodeURIComponent(baseId)}`;
  document.getElementById("compareResult").classList.remove("hidden");
}

document.getElementById("compareBtn").addEventListener("click", async () => {
  const baseId = document.getElementById("compareBaseId").value.trim();
  const candId = document.getElementById("compareCandidateId").value.trim();
  const errEl = document.getElementById("compareError");
  errEl.classList.add("hidden");
  try {
    if (!baseId || !candId) throw new Error("Enter both run IDs.");
    const resp = await fetch(`/quick-eval/${encodeURIComponent(candId)}/compare?base_run_id=${encodeURIComponent(baseId)}`);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || resp.statusText);
    renderComparison(data, baseId, candId);
  } catch (err) {
    errEl.textContent = `Error: ${err.message}`;
    errEl.classList.remove("hidden");
  }
});
