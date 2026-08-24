from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_payment_due_card_keeps_count_and_adds_filtered_amount_total():
    dashboard_js = (ROOT / "app" / "static" / "v811.js").read_text()
    dashboard_css = (ROOT / "app" / "static" / "v811.css").read_text()

    assert 'key === "payments_due"' in dashboard_js
    assert "rows.reduce((sum, row) => sum + Number(row.amount || 0), 0)" in dashboard_js
    assert '${money(paymentTotal)} total due' in dashboard_js
    assert "queueCard(key, queues[key])" in dashboard_js
    assert ".v819-payment-total" in dashboard_css


def test_current_build_identifier_is_exposed_by_health_endpoint():
    backup_py = (ROOT / "app" / "backup.py").read_text()
    assert 'BACKUP_BUILD = "2026.08.24-visible-record-actions-v8.28.3"' in backup_py


def test_upcoming_weddings_are_before_the_work_queues():
    dashboard_js = (ROOT / "app" / "static" / "v811.js").read_text()

    assert "d.upcoming_weddings" in dashboard_js
    assert dashboard_js.index("v824-upcoming-weddings") < dashboard_js.index("v811-queue-cards")
