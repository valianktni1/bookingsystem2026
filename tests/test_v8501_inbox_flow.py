from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_inbox_filter_is_independent_and_never_silently_uses_workspace_search():
    mail = (ROOT / "app" / "static" / "v896.js").read_text()
    assert 'state.mailFilter = ""' in mail
    assert 'const query = String(state.mailFilter || "")' in mail
    assert 'const query = String(state.search || "")' not in mail
    assert 'id="mail-filter-input"' in mail
    assert 'id="mail-clear-filter"' in mail
    assert "Show all emails" in mail


def test_normal_and_couple_inbox_routes_have_distinct_clear_behaviour():
    mail = (ROOT / "app" / "static" / "v896.js").read_text()
    app = (ROOT / "app" / "static" / "app.js").read_text()
    mobile = (ROOT / "app" / "static" / "v8301.js").read_text()
    assert "window.openFullMailbox" in mail
    assert "window.openMailboxForAddress" in mail
    assert "button.onclick = window.openFullMailbox" in mail
    assert "window.openMailboxForAddress(r.client.email" in app
    assert 'button.dataset.mobileJump === "mail" ? window.openFullMailbox()' in mobile


def test_v8501_build_identity_and_fresh_inbox_assets():
    index = (ROOT / "app" / "static" / "index.html").read_text()
    backup = (ROOT / "app" / "backup.py").read_text()
    assert "BOOKINGSYSTEM2026 · COMPLETE V8.50.2" in index
    assert "inbox-flow-v8-50-1" in index
    assert 'BACKUP_BUILD = "2026.09.17-workflow-cleanup-v8.50.2"' in backup
