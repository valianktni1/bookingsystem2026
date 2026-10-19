from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_final_timings_review_hides_internal_workings_by_default():
    script = (ROOT / "app/static/v874.js").read_text(encoding="utf-8")
    assert 'submission.form_type === "final_timings"' in script
    for key in ("_calculation", "_form_template", "_answer_snapshot", "_template_revision"):
        assert f'"{key}"' in script
    assert "SUGGESTED START" in script
    assert "EXPECTED FINISH" in script
    assert "TOTAL COVERAGE" in script
    assert "Contacts & important notes" in script
    assert '<details class="v874-all-answers">' in script
    assert '<details class="v874-technical">' in script
    assert '<details class="v874-technical" open>' not in script


def test_release_assets_are_loaded_after_existing_workspace_scripts():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert '/static/v874.css?v=final-timings-review-v8-74' in html
    assert '/static/v874.js?v=final-timings-review-v8-74' in html
    assert html.index('/static/v874.js') > html.index('/static/v871.js')


def test_mobile_and_dark_mode_rules_are_present():
    css = (ROOT / "app/static/v874.css").read_text(encoding="utf-8")
    assert '@media(max-width:760px)' in css
    assert 'html[data-wbm-theme="dark"] .v874-summary' in css
    assert '.v874-review-grid{grid-template-columns:1fr' in css
