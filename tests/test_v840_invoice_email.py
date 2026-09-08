import importlib
from tests.test_v834_invoice_amendments import (reset_database, login, create_accepted_invoice)
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Booking, EmailLog, Invoice
from sqlalchemy import select


def test_invoice_pdf_and_manual_send_for_imported_booking(monkeypatch):
    reset_database()
    service = importlib.import_module('app.email_service')
    main = importlib.import_module('app.main')
    messages = []
    monkeypatch.setattr(service, 'smtp_ready', lambda brand: True)
    monkeypatch.setattr(main, 'smtp_credentials', lambda brand: ('sender@example.com', 'unused'))
    monkeypatch.setattr(service, 'send_email_message', lambda message, brand: messages.append(message))
    with TestClient(app) as client:
        booking_id, invoice_id, number = create_accepted_invoice(legacy=True)
        with SessionLocal() as db:
            booking = db.get(Booking, booking_id)
            booking.automation_suppressed = True
            db.commit()
        url = f'/api/invoices/{invoice_id}'
        assert client.get(url+'/pdf').status_code == 401
        assert client.get(url+'/email').status_code == 401
        login(client)
        pdf = client.get(url+'/pdf?inline=true')
        assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
        draft = client.get(url+'/email').json()
        assert draft['recipient'] == 'sophie@example.com'
        assert draft['manual_only'] is True
        payload = {'mode': 'manual', 'subject': draft['subject'], 'body': draft['body']}
        assert client.post(url+'/email', json=payload).status_code == 422
        assert not messages
        payload.update(manual_confirmation='SEND ONE MANUAL EMAIL', manual_reason='Requested invoice')
        sent = client.post(url+'/email', json=payload)
        assert sent.status_code == 200, sent.text
        attachments = list(messages[0].iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_filename() == number+'.pdf'
        assert attachments[0].get_payload(decode=True).startswith(b'%PDF')
        assert messages[0]['To'] == draft['recipient']
        with SessionLocal() as db:
            assert db.get(Booking, booking_id).automation_suppressed is True
            log = db.scalar(select(EmailLog).where(EmailLog.booking_id == booking_id))
            assert log.status == 'sent' and log.template_key == 'manual_invoice'
            db.get(Invoice, invoice_id).status = 'void'
            db.commit()
        assert client.post(url+'/email', json=payload).status_code == 409
        assert len(messages) == 1


def test_normal_invoice_test_recipient_and_smtp_failure(monkeypatch):
    reset_database()
    service = importlib.import_module('app.email_service')
    main = importlib.import_module('app.main')
    monkeypatch.setattr(service, 'smtp_ready', lambda brand: True)
    monkeypatch.setattr(main, 'smtp_credentials', lambda brand: ('sender@example.com', 'unused'))
    def fail(message, brand):
        assert message['To'] == 'safe@example.com'
        raise RuntimeError('private SMTP detail')
    monkeypatch.setattr(service, 'send_email_message', fail)
    with TestClient(app) as client:
        login(client)
        booking_id, invoice_id, _ = create_accepted_invoice()
        with SessionLocal() as db:
            booking = db.get(Booking, booking_id)
            booking.is_test = True
            booking.workflow_state = {'test_email': 'safe@example.com'}
            db.commit()
        url = f'/api/invoices/{invoice_id}/email'
        draft = client.get(url).json()
        assert draft['recipient'] == 'safe@example.com'
        payload = {'mode': 'manual', 'subject': draft['subject'], 'body': draft['body']}
        response = client.post(url, json=payload)
        assert response.status_code == 503
        assert 'private SMTP detail' not in response.text
        with SessionLocal() as db:
            log = db.scalar(select(EmailLog).where(EmailLog.booking_id == booking_id))
            assert log.status == 'failed'
