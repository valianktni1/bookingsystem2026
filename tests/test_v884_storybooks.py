"""Local API exercises: no live enquiries, bank transactions or mail."""
from datetime import date, timedelta
from uuid import uuid4
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app import main, enquiry_delivery
from app.database import Base, get_db
from app.models import (Admin, Booking, Brand, BusinessProfile, Client, EmailLog, Invoice,
                        RecordKind, RecordStatus, SystemSetting)
from app.security import current_admin
from app.storybooks import StorybookOrder, _hits


@pytest.fixture
def setup(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    def dependency():
        with sessions() as db:
            yield db
    main.app.dependency_overrides[get_db] = dependency
    main.app.dependency_overrides[current_admin] = lambda: Admin(email="mark@example.com")
    monkeypatch.setattr(enquiry_delivery, "SessionLocal", sessions)
    smtp = Mock()
    monkeypatch.setattr(enquiry_delivery, "send_rendered_email", smtp)
    calendar = Mock(side_effect=AssertionError("Storybook payment must not sync a wedding"))
    monkeypatch.setattr(main, "sync_booking_calendar_safely", calendar)
    _hits.clear()
    with sessions() as db:
        db.add(BusinessProfile(brand=Brand.WBM, display_name="Example studio", invoice_prefix="WBM"))
        db.commit()
    yield TestClient(main.app), sessions, smtp, calendar
    main.app.dependency_overrides.clear()
    engine.dispose()


def request():
    return {
        "submission_id": str(uuid4()), "buyer_name": "Adult Gift Buyer", "buyer_email": "buyer@example.com",
        "privacy_agreed": True,
        "details": {
            "wedding_date": "2022-10-20", "venue": "St John's", "ceremony": "church_separate",
            "reception": "Old Hall", "gift": True,
            "books": [
                {"name": "ExampleOne", "role": "flower_girl", "hair": "blonde", "dedication": "Love from the family"},
                {"name": "ExampleTwo", "role": "pageboy", "hair": "other", "hair_other": "Silver brown"}
            ]
        }
    }


def wedding(sessions, **updates):
    with sessions() as db:
        client = Client(first_name="Example", last_name="Couple", email="couple@example.com")
        db.add(client); db.flush()
        values = dict(brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.QUOTED,
                      title="Couple wedding", client_id=client.id, event_date=date.today()+timedelta(days=30),
                      venue_or_project="Original Hall", deposit_amount=100)
        values.update(updates)
        record = Booking(**values)
        db.add(record); db.flush()
        raw, _ = main.issue_portal_token(db, record.id)
        db.commit()
        return record.id, raw


def test_public_order_invoice_payment_and_fulfilment(setup):
    client, sessions, smtp, calendar = setup
    payload = request()
    assert client.post("/api/public/storybooks", json=payload).status_code == 201
    assert client.post("/api/public/storybooks", json=payload).status_code == 201
    smtp.assert_not_called()
    rows = client.get("/api/storybooks").json()
    assert len(rows) == 1
    assert client.get("/api/bookings").json() == []
    assert client.get("/api/dashboard").json()["new_storybooks"] == 1
    row = rows[0]; base = f"/api/storybooks/{row['id']}"
    assert row["total"] == 69.98 and row["stage"] == "new"
    assert len(row["details"]["books"]) == 2
    assert row["details"]["separate_venues"] is True
    enquiry_delivery.run_queued_enquiry_emails()
    enquiry_delivery.run_queued_enquiry_emails()
    smtp.assert_called_once()
    assert smtp.call_args.kwargs["reply_to"] == "buyer@example.com"
    assert "ExampleOne" not in smtp.call_args.args[4]
    changed = client.patch(base, json={
        "buyer_name":"The Paying Adult", "buyer_email":"bill-to@example.com", "billing_address":"1 Bill Street",
        "delivery_name":"Recipient Adult", "delivery_address":"2 Delivery Close, M1 1AA", "details":row["details"]
    })
    assert changed.status_code == 200, changed.text
    inv = client.post(base+"/invoice", json={"due_date":date.today().isoformat()})
    assert inv.status_code == 201, inv.text
    invoice = inv.json()
    assert invoice["total"] == 69.98
    assert invoice["line_items"][0]["quantity"] == 2
    assert invoice["line_items"][0]["unit_price"] == 34.99
    assert invoice["payment_reference"] == invoice["number"]
    assert "ExampleOne" not in inv.text and "Recipient Adult" not in inv.text
    assert client.post(base+"/invoice", json={"due_date":date.today().isoformat()}).json()["id"] == invoice["id"]
    path = f"/api/invoices/{invoice['id']}"
    assert client.get(path+"/email").json()["recipient"] == "bill-to@example.com"
    pdf = client.get(path+"/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.post(base+"/fulfilment", json={"stage":"sent_to_print"}).status_code == 409
    assert client.post(path+"/payments", json={"amount":"34.99"}).json()["status"] == "part_paid"
    assert client.get("/api/storybooks").json()[0]["stage"] == "invoiced"
    assert client.post(base+"/fulfilment", json={"stage":"sent_to_print"}).status_code == 409
    assert client.post(path+"/payments", json={"amount":"34.99"}).json()["status"] == "paid"
    assert client.get("/api/storybooks").json()[0]["stage"] == "paid"
    assert client.post(base+"/fulfilment", json={"stage":"sent_to_print"}).json()["stage"] == "sent_to_print"
    assert client.post(base+"/fulfilment", json={"stage":"dispatched"}).json()["stage"] == "dispatched"
    assert client.get(path+"/receipt.pdf").status_code == 200
    calendar.assert_not_called()
    with sessions() as db:
        booking = db.get(Booking, row["billing_id"])
        assert not booking.event_date and not booking.deposit_paid_date
        assert main._workflow_candidates(db, booking) == []
        assert len(db.scalars(select(Invoice)).all()) == 1


def test_couple_order_keeps_booking_and_pdf_access_separate(setup):
    client, sessions, smtp, calendar = setup
    bid, token = wedding(sessions)
    _, other = wedding(sessions)
    payload = request()
    del payload["buyer_name"], payload["buyer_email"]
    assert client.post(f"/api/client/{token}/storybooks", json=payload).status_code == 201
    assert client.post("/api/client/invalid/storybooks", json=payload).status_code == 404
    order = client.get(f"/api/storybooks?wedding_id={bid}").json()[0]
    assert order["details"]["venue"] == "St John's"
    inv = client.post(f"/api/storybooks/{order['id']}/invoice", json={"due_date":date.today().isoformat()}).json()
    iid = inv["id"]
    for tok, code in ((token,200),(other,404)):
        assert client.get(f"/api/client/{tok}/storybooks/invoices/{iid}/invoice.pdf").status_code == code
    pay = client.post(f"/api/invoices/{iid}/payments", json={"amount":"69.98"})
    assert pay.status_code == 201, pay.text
    pid = pay.json()["payments"][0]["id"]
    assert client.delete(f"/api/payments/{pid}").status_code == 204
    assert client.get("/api/storybooks").json()[0]["stage"] == "invoiced"
    with sessions() as db:
        record = db.get(Booking, bid)
        assert record.venue_or_project == "Original Hall"
        assert record.status == RecordStatus.QUOTED and record.deposit_amount == 100
        assert record.deposit_paid_date is None and not record.invoices
    calendar.assert_not_called()


@pytest.mark.parametrize("field", ["other_hair", "venue_split", "copies", "consent"])
def test_invalid_order_is_rejected_without_writing(setup, field):
    client, sessions, _, _ = setup
    p = request()
    if field == "other_hair": p["details"]["books"][1]["hair_other"] = ""
    if field == "venue_split": p["details"]["reception"] = None
    if field == "copies": p["details"]["books"][0]["quantity"] = 24
    if field == "consent": p["privacy_agreed"] = False
    assert client.post("/api/public/storybooks", json=p).status_code == 422
    with sessions() as db:
        assert db.scalars(select(StorybookOrder)).all() == []


def test_honeypot_permissions_and_testing_mode(setup):
    client, sessions, smtp, _ = setup
    p = request(); p["website"] = "spam"
    assert client.post("/api/public/storybooks", json=p).json() == {"ok":True}
    assert client.get("/api/storybooks").json() == []
    with sessions() as db:
        db.add(SystemSetting(key="testing_mode", value={"enabled":True,"email":"test@example.com"}))
        db.commit()
    p.pop("website")
    assert client.post("/api/public/storybooks", json=p).status_code == 201
    enquiry_delivery.run_queued_enquiry_emails()
    assert smtp.call_args.args[2] == smtp.call_args.kwargs["reply_to"] == "test@example.com"
    del main.app.dependency_overrides[current_admin]
    assert client.get("/api/storybooks").status_code == 401
    assert client.get("/storybook-order").status_code == 200
    assert client.get("/storybooks").status_code == 200


@pytest.mark.parametrize("theme", ["christmas", "holiday", "christmas_wedding"])
def test_new_themes_validate_and_invoice_at_agreed_price(setup, theme):
    client, _, _, _ = setup
    payload = request()
    details = payload["details"]
    details.update(theme=theme, destination="Cornwall")
    if theme != "christmas_wedding":
        for key in ("wedding_date", "venue", "ceremony", "reception"):
            details.pop(key)
        for book in details["books"]:
            book["role"] = "child"
    else:
        missing_venue = {**payload, "details": {**details, "venue": None}}
        assert client.post("/api/public/storybooks", json=missing_venue).status_code == 422
    invalid = {**payload, "details": {**details, "theme": "unknown"}}
    assert client.post("/api/public/storybooks", json=invalid).status_code == 422
    response = client.post("/api/public/storybooks", json=payload)
    assert response.status_code == 201, response.text
    row = client.get("/api/storybooks").json()[0]
    assert row["details"]["theme"] == theme
    assert row["details"]["destination"] == ("Cornwall" if theme == "holiday" else None)
    assert row["total"] is None
    path = f"/api/storybooks/{row['id']}/invoice"
    invoice = {"due_date": (date.today() + timedelta(days=1)).isoformat()}
    assert client.post(path, json=invoice).status_code == 422
    assert client.post(path, json={**invoice, "unit_price":"39.995"}).status_code == 422
    result = client.post(path, json={**invoice, "unit_price":"39.95"})
    assert result.status_code == 201, result.text
    assert result.json()["total"] == 79.90
    assert result.json()["line_items"][0]["unit_price"] == 39.95
    assert client.get("/api/storybooks").json()[0]["total"] == 79.90


def test_public_editor_preserves_order_and_invoice_when_story_changes(setup):
    client, _, smtp, _ = setup
    public = "/api/public/storybooks/form"
    editor = "/api/storybooks/form"
    initial = client.get(public)
    assert initial.headers["cache-control"] == "no-store"
    assert "ivorydigital.uk" in client.get("/storybook-order").headers["content-security-policy"]
    assert "ivorydigital.uk" not in client.get("/enquiry").headers["content-security-policy"]
    config = client.get(editor).json()["config"]
    story = "story_" + uuid4().hex
    question = uuid4().hex
    config["stories"][1]["enabled"] = False
    config["stories"].append({"id": story, "label": "Birthday Book"})
    config["questions"] = [{"id": question, "label": "Birthday", "kind": "date", "story": story, "required": True}]
    with_override = main.app.dependency_overrides.pop(current_admin)
    try:
        assert client.get(editor).status_code == 401
        assert client.put(editor, json=config).status_code == 401
    finally:
        main.app.dependency_overrides[current_admin] = with_override
    updated = client.put(editor, json=config)
    assert updated.status_code == 200, updated.text
    revision = updated.json()["revision"]
    assert revision == client.get(public).json()["revision"]
    assert not any(s["id"] == "christmas_wedding" for s in client.get(public).json()["config"]["stories"])
    payload = request()
    payload["details"]["theme"] = story
    payload["form_revision"] = initial.json()["revision"]
    assert client.post("/api/public/storybooks", json=payload).status_code == 409
    payload["form_revision"] = revision
    assert client.post("/api/public/storybooks", json=payload).status_code == 422
    payload["answers"] = {question: "not a date"}
    assert client.post("/api/public/storybooks", json=payload).status_code == 422
    payload["answers"][question] = "2027-03-05"
    payload["details"]["theme_title"] = "Not the saved title"
    payload["details"]["custom_answers"] = [{"question": "Injected", "answer": "ignored"}]
    saved = client.post("/api/public/storybooks", json=payload)
    assert saved.status_code == 201, saved.text
    config["stories"].pop()
    config["questions"].clear()
    assert client.put(editor, json=config).status_code == 200
    assert client.post("/api/public/storybooks", json=payload).status_code == 201  # safe retry, including after form changes
    payload["submission_id"] = str(uuid4())
    payload["form_revision"] = client.get(public).json()["revision"]
    assert client.post("/api/public/storybooks", json=payload).status_code == 422
    [order] = client.get("/api/storybooks").json()
    assert order["details"]["theme_title"] == "Birthday Book"
    assert order["details"]["custom_answers"] == [{"question": "Birthday", "answer": "2027-03-05"}]
    assert order["total"] is None
    base = f"/api/storybooks/{order['id']}"
    details = order["details"]
    details.pop("custom_answers")
    client_edit = client.patch(base, json={"buyer_name": order["buyer_name"], "buyer_email": order["buyer_email"], "details": details})
    assert client_edit.status_code == 200 and client_edit.json()["details"]["custom_answers"]
    due = date.today().isoformat()
    assert client.post(base + "/invoice", json={"due_date": due}).status_code == 422
    invoice = client.post(base + "/invoice", json={"due_date": due, "unit_price": "39.99"})
    assert invoice.status_code == 201, invoice.text
    assert invoice.json()["line_items"][0]["name"] == "Personalised Birthday Book (hardback)"
    smtp.assert_not_called()
