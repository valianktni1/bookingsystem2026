import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / 'tests/test-v842.db'}")
os.environ.setdefault("STORAGE_ROOT", str(ROOT / "tests/v842-storage"))
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("ADMIN_EMAIL", "mark@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "SecureTestPassword!123")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters-long")


from app import mail_service
from app.models import Brand


def test_dashboard_does_not_wait_for_live_mailbox():
    script = (ROOT / "app/static/v811.js").read_text(encoding="utf-8")
    blocking = "Promise.all([workflowRequest, mailRequest])"
    first_render = script.index("renderTodayDashboard(data, renderNumber)")
    mailbox_load = script.index("loadDashboardMail().then")

    assert blocking not in script
    assert "setMode();" not in script
    assert first_render < mailbox_load
    assert "A slow external mailbox must never" in script
    assert 'section: "Emails"' in script


def test_direct_email_workspace_is_loaded_on_desktop_and_mobile():
    index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    app = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    navigation = (ROOT / "app/static/v811.js").read_text(encoding="utf-8")
    mobile = (ROOT / "app/static/v8301.js").read_text(encoding="utf-8")
    shortcuts = (ROOT / "app/static/v832.js").read_text(encoding="utf-8")

    assert "BOOKINGSYSTEM2026 · COMPLETE V8.47" in index
    assert 'Emails: "emails"' in navigation
    assert '["Emails", "✉", "Emails"]' in navigation
    assert 'selected==="Emails"' in app
    assert "Email delivery, opens and replies" in app
    assert 'data-email-compose' in app
    assert '{tab: "Emails", icon: "✉", label: "Emails"' in mobile
    assert 'selectRecordTab(record, "Emails", true)' in shortcuts


def test_mailbox_header_cache_returns_safe_copies_and_honours_refresh(monkeypatch):
    mail_service._inbox_cache.clear()
    calls = []

    def fetch(brand, count, unread_only):
        calls.append((brand, count, unread_only))
        return [
            {"uid": "2", "brand": brand.value, "unread": True, "date": "2026-09-08T12:00:00+00:00"},
            {"uid": "1", "brand": brand.value, "unread": False, "date": "2026-09-08T11:00:00+00:00"},
        ]

    monkeypatch.setattr(mail_service, "_fetch_inbox_messages_uncached", fetch)
    first = mail_service.list_inbox_messages(Brand.WBM, 200)
    first[0]["booking"] = {"id": "must-not-leak"}
    repeated = mail_service.list_inbox_messages(Brand.WBM, 200)
    unread = mail_service.list_inbox_messages(Brand.WBM, 30, unread_only=True)

    assert len(calls) == 1
    assert "booking" not in repeated[0]
    assert [row["uid"] for row in unread] == ["2"]

    mail_service.list_inbox_messages(Brand.WBM, 200, force_refresh=True)
    assert len(calls) == 2
