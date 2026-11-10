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
