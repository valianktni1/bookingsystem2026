"""Isolated SQLite requests and mocked SMTP; never uses live records or email."""
import os
from unittest.mock import Mock

os.environ.update(DATABASE_URL='sqlite:////tmp/wbm-v883-enquiry-test.db',
                  STORAGE_ROOT='/tmp/wbm-v883-enquiry-storage',
                  SESSION_SECRET='isolated-enquiry-response-tests-only-32')
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app import main
from app import enquiry_delivery as delivery
from app.database import Base, engine, SessionLocal
from app.models import BusinessProfile, EmailTemplate, FormTemplate, Booking, Client, EmailLog, Brand, SystemSetting
from app.enquiry_forms import DEFAULT_ENQUIRY_FORM


@pytest.fixture(autouse=True)
def fixture(monkeypatch):
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    main.ENQUIRY_HITS.clear()
    monkeypatch.setattr(main, 'smtp_ready', lambda *a: True)
    smtp = Mock(side_effect=AssertionError('SMTP must not run during HTTP submission'))
    monkeypatch.setattr(main, 'send_template_email', smtp)
    monkeypatch.setattr(delivery, 'send_rendered_email', smtp)
    with SessionLocal() as db:
        db.add(BusinessProfile(brand=Brand.WBM, display_name='Example studio', invoice_prefix='WBM'))
        db.add(FormTemplate(brand=Brand.WBM, template_key='website_enquiry', display_name='Website', config=DEFAULT_ENQUIRY_FORM))
        for key in delivery.KEYS:
            db.add(EmailTemplate(brand=Brand.WBM, template_key=key, display_name=key,
                                subject='Hello {client_first_name}', body='Received {couple_or_company}. {portal_url} {enquiry_message}'))
        db.commit()
    yield smtp


def submit():
    # No TestClient lifespan: queue delivery cannot race the assertion.
    return TestClient(main.app).post('/api/public/enquiries', json={
        'primary_first_name':'Example', 'partner_first_name':'Partner',
        'email':'example@example.com', 'event_date':'2027-06-12',
        'location':'Example venue', 'heard_about_us':'Google search',
        'privacy_agreed':True, 'message':'Example enquiry'})


def test_response_persists_enquiry_and_mail_without_calling_smtp(fixture):
    response = submit()
    assert response.status_code == 201, response.text
    assert response.json()['ok']
    fixture.assert_not_called()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Booking)) == 1
        emails = db.scalars(select(EmailLog)).all()
        assert len(emails) == 2 and all(e.status == 'queued' for e in emails)
        assert db.scalar(select(func.count()).select_from(delivery.EnquiryEmailJob)) == 2
        ids = [e.id for e in emails]
    # A new connection/worker sees persisted jobs, as after an app restart.
    send = Mock(); delivery.send_rendered_email = send
    delivery.run_queued_enquiry_emails()
    assert send.call_count == 2
    delivery.run_queued_enquiry_emails()
    assert send.call_count == 2
    with SessionLocal() as db:
        assert all(db.get(EmailLog, i).status == 'sent' for i in ids)
        ack = db.scalar(select(EmailLog).where(EmailLog.template_key == 'enquiry_received'))
        job = db.get(delivery.EnquiryEmailJob, ack.id)
        token = job.open_tracking_url.rsplit('/', 1)[-1][:-4]
        assert 'email_access='+token in ack.body
        import hashlib
        assert ack.tracking_token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert ack.recipient == 'example@example.com'
        owner = db.scalar(select(EmailLog).where(EmailLog.template_key == 'new_enquiry_admin'))
        assert db.get(delivery.EnquiryEmailJob, owner.id).reply_to == 'example@example.com'


def test_duplicate_submission_does_not_queue_again(fixture):
    assert submit().status_code == 201
    assert submit().json()['duplicate_ignored']
    fixture.assert_not_called()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Booking)) == 1
        assert db.scalar(select(func.count()).select_from(Client)) == 1
        assert db.scalar(select(func.count()).select_from(delivery.EnquiryEmailJob)) == 2


def test_failure_is_visible_without_automatic_resend(monkeypatch):
    assert submit().status_code == 201
    send = Mock(side_effect=TimeoutError('SMTP confirmation uncertain'))
    monkeypatch.setattr(delivery, 'send_rendered_email', send)
    delivery.run_queued_enquiry_emails(); delivery.run_queued_enquiry_emails()
    assert send.call_count == 2
    with SessionLocal() as db:
        assert all(e.status == 'failed' and e.body and 'uncertain' in e.error for e in db.scalars(select(EmailLog)))
        assert db.scalar(select(func.count()).select_from(Booking)) == 1


def test_queue_claim_and_saved_wording_are_respected(monkeypatch):
    assert submit().status_code == 201
    with SessionLocal() as db:
        email = db.scalar(select(EmailLog).where(EmailLog.template_key == 'enquiry_received'))
        retained = email.body; eid = email.id
        template = db.scalar(select(EmailTemplate).where(EmailTemplate.template_key == 'enquiry_received'))
        template.body = 'Changed after submission'; db.commit()
    send = Mock(); monkeypatch.setattr(delivery, 'send_rendered_email', send)
    delivery.deliver_one(eid); delivery.deliver_one(eid)
    assert send.call_count == 1
    assert send.call_args.args[4] == retained


def test_protected_import_never_delivered(monkeypatch):
    assert submit().status_code == 201
    with SessionLocal() as db:
        b = db.scalar(select(Booking)); b.legacy_source = 'studio_ninja'; db.commit()
    send = Mock(); monkeypatch.setattr(delivery, 'send_rendered_email', send)
    delivery.run_queued_enquiry_emails(); send.assert_not_called()


def test_test_mode_destination_is_retained(fixture):
    with SessionLocal() as db:
        db.add(SystemSetting(key='testing_mode', value={'enabled':True, 'email':'test-only@example.com'})); db.commit()
    assert submit().status_code == 201
    with SessionLocal() as db:
        ack = db.scalar(select(EmailLog).where(EmailLog.template_key == 'enquiry_received'))
        assert ack.recipient == 'test-only@example.com'
    fixture.assert_not_called()


def test_queue_rolls_back_with_unsaved_enquiry(monkeypatch):
    assert submit().status_code == 201
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(EmailLog))
        b = db.scalar(select(Booking))
        p = db.scalar(select(BusinessProfile))
        t = db.scalar(select(EmailTemplate).where(EmailTemplate.template_key == 'enquiry_received'))
        delivery.queue_enquiry_email(db, b, p, t, recipient='example@example.com', portal_url='https://example.invalid/client/example')
        db.rollback()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(EmailLog)) == before
        assert db.scalar(select(func.count()).select_from(delivery.EnquiryEmailJob)) == before
