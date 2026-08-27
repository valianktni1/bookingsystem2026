from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mobile_workspace_assets_and_five_item_navigation_are_loaded():
    index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/v8301.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/v8301.css").read_text(encoding="utf-8")

    assert "/static/v8301.css?v=studio-mobile-workspace-v8-30-1" in index
    assert "/static/v8301.js?v=studio-mobile-workspace-v8-30-1" in index
    assert "EMAIL OPENING V8.31" in index
    for view in ("dashboard", "enquiries", "weddings", "calendar", "invoices"):
        assert f'data-view="{view}"' in index
    assert "v8301-mobile-shortcuts" in script
    assert "v8301-mobile-sections" in script
    assert "Couple & wedding" in script
    assert "Quote & mail" in script
    assert "Invoices & payments" in script
    assert "Agreement & forms" in script
    assert "@media(max-width:760px)" in css
    assert ".v830-booking-head{display:none}" in css


def test_mobile_workspace_preserves_safety_language_and_controls():
    script = (ROOT / "app/static/v8301.js").read_text(encoding="utf-8")
    index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")

    assert "renderTab(record, selected, body)" in script
    assert "mobileDashboardShortcutsV8301" in script
    # Compatibility controls stay in the DOM so the established handlers do not break.
    assert 'id="mobile-add" class="hidden"' in index
    assert 'id="mobile-more" class="hidden"' in index
