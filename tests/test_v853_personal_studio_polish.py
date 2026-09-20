from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v853_personal_studio_polish_is_complete():
    index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    search = (ROOT / "app/static/v811.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/v853.css").read_text(encoding="utf-8")
    script = (ROOT / "app/static/v853.js").read_text(encoding="utf-8")
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    backup = (ROOT / "app/backup.py").read_text(encoding="utf-8")

    assert "/static/v853.css?v=personal-studio-polish-v8-53" in index
    assert "/static/v853.js?v=personal-studio-polish-v8-53" in index
    assert "BOOKINGSYSTEM2026 · COMPLETE V8.53" in index
    assert 'data-view="mail"' in index and 'id="mobile-mail-count"' in index
    assert 'id="mobile-more" type="button"' in index
    assert 'id="mobile-add" class="hidden"' in index
    assert "ukDate" in search and "fmtEventDate(record.event_date)" in search
    assert "wedding date" in search
    assert "focus-visible" in css and "prefers-reduced-motion" in css
    assert "mirrorUnreadCount" in script and 'aria-current' in script
    assert 'version="2.8.53"' in main
    assert 'BACKUP_BUILD = "2026.09.19-personal-studio-polish-v8.53"' in backup
