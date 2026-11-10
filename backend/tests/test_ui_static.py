"""Static checks on the UI copy and wiring (no browser)."""
import re
from pathlib import Path

UI = Path(__file__).resolve().parents[2] / "ui"


def test_index_wires_demo_banner_and_packs():
    html = (UI / "index.html").read_text()
    js = (UI / "app.js").read_text()
    assert 'id="demoBanner"' in html and "Public demo only" in html
    assert 'value="financial_services"' in html
    assert '"/health"' in js and 'info.deployment === "demo"' in js
    # every element id the script looks up exists in the page
    for el_id in set(re.findall(r'getElementById\("([A-Za-z]+)"\)', js)):
        assert f'id="{el_id}"' in html, el_id


def test_leaderboard_de_emphasised_not_deleted():
    html = (UI / "index.html").read_text()
    assert 'id="lbBody"' not in html and "Share my score" not in html
    assert (UI / "leaderboard.html").exists()


def test_methodology_has_no_retracted_claims():
    page = (UI / "methodology.html").read_text()
    for phrase in ("chain-of-thought forcing", "Llama-3.3-70b) to evaluate", "formatting is stripped", "2604.23178"):
        assert phrase not in page
    assert "Provisional" in page


def test_failures_show_how_each_case_was_decided():
    js = (UI / "app.js").read_text()
    assert 'injection_resisted: "Injection resisted (graded in code)"' in js
    assert "r.decided_by" in js and "jr.evidence" in js and "jr.attack_goal" in js
    page = (UI / "methodology.html").read_text()
    assert "graded on actions, in code" in page and "2603.06594" in page


def test_compare_view_shows_flipped_cases():
    html = (UI / "index.html").read_text()
    js = (UI / "app.js").read_text()
    assert 'id="compareSection"' in html and 'id="rerunOf"' in html
    assert "/compare?base_run_id=" in js and "/compare/report?base_run_id=" in js
    for field in ("d.prompt", "d.base_answer", "d.candidate_answer", "d.candidate_decided_by", "d.evidence"):
        assert field in js
    assert "rerun_of: rerunOf" in js


def test_compare_view_redacts_harmful_answers_and_shows_release():
    js = (UI / "app.js").read_text()
    assert "function compareAnswer" in js and "[harmful content — redacted]" in js and "d.should_refuse" in js
    assert "compareAnswer(d, d.candidate_answer, d.candidate_passed)" in js
    assert "cmp.release.decision" in js and "cmp.release.recommended_action" in js and "d.impact" in js
    assert "improvement${imps.length === 1" in js  # "N regressions · M improvements (of K shared cases)"


def test_compare_view_labels_simulated_models_and_sends_key():
    html = (UI / "index.html").read_text()
    js = (UI / "app.js").read_text()
    assert 'id="compareSimulated"' in html and "Simulated models</strong> — illustrative results" in html
    assert 'startsWith("fake")' in js and 'getElementById("compareSimulated")' in js
    # Outside demo mode compare + report need the key or invite: the fetch sends it, the report opens from a blob.
    assert '/compare?base_run_id=${encodeURIComponent(baseId)}`,\n      { headers: authHeaders() }' in js
    assert "URL.createObjectURL(blob)" in js and '"X-Admin-Key": key' in js


def test_ui_sends_invite_token_from_invite_link():
    js = (UI / "app.js").read_text()
    # /ui/?invite=<token> (the link POST /admin/invite returns) is captured, stripped from the URL and sent.
    assert 'params.get("invite")' in js and 'params.delete("invite")' in js and "history.replaceState" in js
    assert '"X-Invite-Token": invite' in js
    assert "...authHeaders()" in js  # apiFetch
    assert "const reqHeaders = authHeaders();" in js  # POST /quick-eval, polling, final results


def test_methodology_crescendo_figures_match_paper_table_4():
    """arXiv 2404.01833v3, Table 4: average ASR 56.2 / 82.6, binary ASR 98.0 / 100.0 (GPT-4 / Gemini-Pro)."""
    html = (UI / "methodology.html").read_text()
    for needle in ("56.2%", "82.6%", "98%", "100%", "Table 4", "binary", "average", "49 of 50"):
        assert needle in html, needle
    assert "Crescendo achieved 56% ASR against GPT-4" not in html  # the old, metric-less wording


def test_research_notes_doc_exists_and_is_linked():
    root = UI.parent
    doc = (root / "docs" / "research-notes.md").read_text()
    for needle in ("2310.03693", "2505.06843", "2603.06594", "2503.09347", "2406.13352", "2510.05244", "2404.01833",
                   "56.2%", "98.0%", "Checked against"):
        assert needle in doc, needle
    assert "docs/research-notes.md" in (root / "CLAUDE.md").read_text()
    assert "docs/research-notes.md" in (root / "README.md").read_text()


def test_compare_view_shows_significance_and_system_prompt():
    html = (UI / "index.html").read_text()
    js = (UI / "app.js").read_text()
    assert "<th>Significance</th>" in html
    assert "function sigHtml(sig)" in js and "sigHtml((cmp.significance || {}).overall)" in js
    assert "sigHtml(g.significance)" in js
    assert 'compare-k">System prompt' in js and "sp.warning" in js


def test_run_form_offers_system_prompt_mode():
    html = (UI / "index.html").read_text()
    js = (UI / "app.js").read_text()
    for v in ('value="none"', 'value="redline"', 'value="custom"', 'id="customSystemPrompt"'):
        assert v in html, v
    assert "system_prompt_mode: spMode" in js and "custom_system_prompt: spCustom" in js


def test_readme_has_safe_use_guidance_and_current_system_prompt_limitation():
    readme = (UI.parent / "README.md").read_text()
    section = readme.split("## How to use Redline safely", 1)[1].split("\n## ", 1)[0]
    for needle in ("one check, not approval", "real system prompt", "cases for your own tools",
                   "failed cases yourself", "multi-turn", "judge you control", "confidence ranges",
                   "within noise"):
        assert needle in section, needle
    assert "Every request, including requests to your own agent endpoint, is currently sent" not in readme
    assert "system_prompt_mode" in readme


def test_methodology_explains_mcnemar_and_system_prompt():
    html = (UI / "methodology.html").read_text()
    assert "McNemar's exact test" in html and "McNemar, Q. (1947)" in html and "p = 0.0625" in html
    assert "every request is currently sent with Redline's short" not in html
