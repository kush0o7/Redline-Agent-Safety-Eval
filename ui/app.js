function getAdminKey() {
  return document.getElementById("adminKey").value.trim();
}

function getProjectId() {
  return document.getElementById("projectId").value.trim();
}

function requireProjectId() {
  const projectId = getProjectId();
  if (!projectId) {
    throw new Error("Project ID is required. Create a project first.");
  }
  return projectId;
}

function output(value) {
  const el = document.getElementById("output");
  el.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function summarizeResults(summary, results) {
  if (!summary) return "No summary available yet.";
  const lines = [];
  lines.push(`Overall: ${Math.round((summary.pass_rate || 0) * 100)}% passed (${summary.passed}/${summary.total}).`);
  const metrics = summary.metrics || {};
  if (metrics.policy_compliance) {
    const pr = Math.round(metrics.policy_compliance.pass_rate * 100);
    lines.push(`Policy compliance: ${pr}%. Low scores mean it didn't refuse unsafe requests.`);
  }
  if (metrics.hallucination) {
    const hr = Math.round(metrics.hallucination.pass_rate * 100);
    lines.push(`Hallucination control: ${hr}%. Low scores mean it made up details or didn't say \"I don't know.\"`);
  }
  if (metrics.overconfidence) {
    const orr = Math.round(metrics.overconfidence.pass_rate * 100);
    lines.push(`Overconfidence: ${orr}%. Low scores mean it was too confident when uncertain.`);
  }
  if (metrics.refusal_correctness) {
    const rr = Math.round(metrics.refusal_correctness.pass_rate * 100);
    lines.push(`Refusal correctness: ${rr}%. Low scores mean it refused when it shouldn't or didn't refuse when it should.`);
  }

  if (Array.isArray(results) && results.length) {
    const failed = results.filter((r) => !r.passed);
    lines.push(`Failures: ${failed.length}/${results.length}.`);
    const top = failed.slice(0, 3).map((r) => r.testcase_id);
    if (top.length) {
      lines.push(`Example failing testcases: ${top.join(", ")}.`);
    }
  }
  return lines.join("\n");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function apiFetch(path, options = {}) {
  const headers = options.headers || {};
  const adminKey = getAdminKey();
  if (!adminKey) {
    throw new Error("Admin key is required");
  }
  headers["X-Admin-Key"] = adminKey;
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const resp = await fetch(path, { ...options, headers });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.detail || resp.statusText);
  }
  return data;
}

document.getElementById("createProject").addEventListener("click", async () => {
  try {
    let name = document.getElementById("projectName").value.trim();
    if (!name) {
      name = `project-${Date.now()}`;
      document.getElementById("projectName").value = name;
    }
    const data = await apiFetch("/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    document.getElementById("projectId").value = data.id;
    output(data);
  } catch (err) {
    output(String(err));
  }
});

document.getElementById("runDemo").addEventListener("click", async () => {
  try {
    output("Running demo... this may take ~10-30s.");
    const name = `demo-${Date.now()}`;
    const project = await apiFetch("/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    document.getElementById("projectId").value = project.id;

    await apiFetch(`/projects/${project.id}/seed-testcases`, { method: "POST" });
    const testcases = await apiFetch(`/projects/${project.id}/testcases`);
    const testcaseIds = testcases.slice(0, 5).map((t) => t.id);
    document.getElementById("testcaseIds").value = testcaseIds.join(", ");

    const run = await apiFetch(`/projects/${project.id}/runs`, {
      method: "POST",
      body: JSON.stringify({
        testcase_ids: testcaseIds,
        mode: "baseline",
        llm_model: null,
        seed: 7,
      }),
    });
    document.getElementById("runId").value = run.run_id;

    let summary = null;
    for (let i = 0; i < 20; i++) {
      await sleep(1000);
      summary = await apiFetch(`/projects/${project.id}/runs/${run.run_id}`);
      if (summary.status === "completed" || summary.status === "failed") {
        break;
      }
    }
    const results = await apiFetch(`/projects/${project.id}/runs/${run.run_id}/results`);
    output({ project, run: summary, results });
  } catch (err) {
    output(String(err));
  }
});

document.getElementById("seedTestcases").addEventListener("click", async () => {
  try {
    const projectId = requireProjectId();
    output("Seeding default testcases...");
    const data = await apiFetch(`/projects/${projectId}/seed-testcases`, { method: "POST" });
    output(data);
  } catch (err) {
    output(String(err));
  }
});

document.getElementById("listTestcases").addEventListener("click", async () => {
  try {
    const projectId = requireProjectId();
    const data = await apiFetch(`/projects/${projectId}/testcases`);
    document.getElementById("testcaseIds").value = data.map((t) => t.id).join(", ");
    output(data);
  } catch (err) {
    output(String(err));
  }
});

document.getElementById("createRun").addEventListener("click", async () => {
  try {
    const projectId = requireProjectId();
    const testcaseIds = document.getElementById("testcaseIds").value
      .split(",")
      .map((id) => id.trim())
      .filter(Boolean);
    const mode = document.getElementById("runMode").value;
    const llmModel = document.getElementById("runModel").value.trim() || null;
    const seed = Number(document.getElementById("runSeed").value || 0);
    const data = await apiFetch(`/projects/${projectId}/runs`, {
      method: "POST",
      body: JSON.stringify({ testcase_ids: testcaseIds, mode, llm_model: llmModel, seed }),
    });
    document.getElementById("runId").value = data.run_id;
    output(data);
  } catch (err) {
    output(String(err));
  }
});

document.getElementById("getRun").addEventListener("click", async () => {
  try {
    const projectId = requireProjectId();
    const runId = document.getElementById("runId").value.trim();
    const data = await apiFetch(`/projects/${projectId}/runs/${runId}`);
    output(data);
  } catch (err) {
    output(String(err));
  }
});

document.getElementById("getResults").addEventListener("click", async () => {
  try {
    const projectId = requireProjectId();
    const runId = document.getElementById("runId").value.trim();
    const data = await apiFetch(`/projects/${projectId}/runs/${runId}/results`);
    output(data);
  } catch (err) {
    output(String(err));
  }
});

document.getElementById("explainResults").addEventListener("click", async () => {
  try {
    const projectId = requireProjectId();
    const runId = document.getElementById("runId").value.trim();
    const summaryResp = await apiFetch(`/projects/${projectId}/runs/${runId}`);
    const results = await apiFetch(`/projects/${projectId}/runs/${runId}/results`);
    output(summarizeResults(summaryResp.summary, results));
  } catch (err) {
    output(String(err));
  }
});

document.getElementById("getTrace").addEventListener("click", async () => {
  try {
    const projectId = requireProjectId();
    const runId = document.getElementById("runId").value.trim();
    const testcaseId = document.getElementById("traceTestcaseId").value.trim();
    const data = await apiFetch(`/projects/${projectId}/runs/${runId}/traces/${testcaseId}`);
    output(data);
  } catch (err) {
    output(String(err));
  }
});
