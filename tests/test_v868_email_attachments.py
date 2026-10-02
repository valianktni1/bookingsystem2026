import base64
from io import BytesIO
from zipfile import ZipFile

import pytest
from pydantic import ValidationError
from test_v8105_client_email_centre import reset_database, login, create_booking
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.database import SessionLocal
from app.models import Booking, AuditLog, EmailLog
from app.schemas import ClientEmailWithAttachmentsIn
from app.email_attachments import EmailAttachmentIn, MAX_ATTACHMENT_BYTES


def attachment(name='information.pdf', data=b'%PDF-1.7\nexample'):
    return {'filename': name, 'content_base64': base64.b64encode(data).decode()}


def payload(files=None):
    return {'mode': 'manual', 'subject': 'Your information', 'body': 'Hi {client_first_name},\nPlease see attached.', 'attachments': files or []}


@pytest.mark.parametrize('name,data', [
    ('information.pdf', b'%PDF-1.7\nexample'), ('photo.jpeg', b'\xff\xd8\xfftest'),
    ('photo.jpg', b'\xff\xd8\xfftest'), ('photo.png', b'\x89PNG\r\n\x1a\ntest'),
    ('photo.gif', b'GIF89atest'), ('photo.webp', b'RIFF1234WEBPtest'),
    ('notes.doc', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1test'),
])
def test_supported_files(name, data):
    item = EmailAttachmentIn(**attachment(name, data))
    assert item.transport()['data'] == data


def test_word_and_validation():
    doc = BytesIO()
    with ZipFile(doc, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('word/document.xml', '<document/>')
    assert EmailAttachmentIn(**attachment('word.docx', doc.getvalue())).transport()['content_type'].endswith('document')
    assert EmailAttachmentIn(**attachment('C:\\fakepath\\notes.pdf')).filename == 'notes.pdf'
    invalid = [attachment('danger.exe'), attachment('fake.pdf', b'<script>bad</script>'),
               attachment('empty.pdf', b''), attachment('name\r\n.pdf'),
               attachment('wrong.docx', b'PKwrong'), {'filename': 'bad.pdf', 'content_base64': 'invalid!'}]
    for file in invalid:
        with pytest.raises(ValidationError):
            EmailAttachmentIn(**file)
    with pytest.raises(ValidationError):
        ClientEmailWithAttachmentsIn(**payload([attachment()] * 6))
    with pytest.raises(ValidationError):
        ClientEmailWithAttachmentsIn(**payload([attachment(data=b'%PDF-' + b'x' * (MAX_ATTACHMENT_BYTES // 2))] * 2))


def test_real_mime_transport_and_existing_safeguards(monkeypatch):
    reset_database()
    messages = []
    monkeypatch.setattr('app.email_service.smtp_ready', lambda brand: True)
    monkeypatch.setattr('app.email_service.smtp_credentials', lambda brand: ('mark@example.com', 'test'))
    monkeypatch.setattr('app.email_service.send_email_message', lambda message, brand: messages.append(message))
    files = [attachment('Our information.pdf'), attachment('photo.jpeg', b'\xff\xd8\xfftest')]
    with TestClient(app) as client:
        login(client)
        booking = create_booking(client)
        endpoint = f"/api/bookings/{booking['id']}/email-centre/send"
        response = client.post(endpoint, json=payload(files))
        assert response.status_code == 200, response.text
        parts = [part for part in messages[-1].walk() if part.get_content_disposition() == 'attachment']
        assert [part.get_filename() for part in parts] == ['Our information.pdf', 'photo.jpeg']
        assert parts[0].get_payload(decode=True) == b'%PDF-1.7\nexample'
        assert parts[1].get_content_type() == 'image/jpeg'
        assert messages[-1]['To'] == 'alex@example.com'
        assert any(part.get_content_type() == 'text/html' for part in messages[-1].walk())
        assert '/client/' in messages[-1].get_body(preferencelist=('plain',)).get_content()
        with SessionLocal() as db:
            logs = db.scalars(select(AuditLog).where(AuditLog.entity_id == booking['id'])).all()
            assert any('Our information.pdf' in str(log.__dict__) for log in logs)
            row = db.get(Booking, booking['id'])
            row.legacy_source = 'studio_ninja'
            row.automation_suppressed = True
            db.commit()
        assert client.post(endpoint, json=payload(files)).status_code == 422
        assert len(messages) == 1
        approved = {**payload(files), 'manual_confirmation': 'SEND ONE MANUAL EMAIL', 'manual_reason': 'Requested information'}
        assert client.post(endpoint, json=approved).status_code == 200
        assert len(messages) == 2
        with SessionLocal() as db:
            row = db.get(Booking, booking['id'])
            assert row.automation_suppressed
            row.is_test = True
            row.workflow_state = {'test_email': 'testing@example.com'}
            db.commit()
        assert client.post(endpoint, json=approved).status_code == 200
        assert messages[-1]['To'] == 'testing@example.com'
        assert client.post(endpoint, json={**approved, 'attachments': [attachment('bad.exe')]}).status_code == 422
        assert len(messages) == 3
        def fail(message, brand):
            raise RuntimeError('Test transport unavailable')
        monkeypatch.setattr('app.email_service.send_email_message', fail)
        assert client.post(endpoint, json=approved).status_code == 503

        with SessionLocal() as db:
            failed = db.scalar(select(EmailLog).where(EmailLog.booking_id == booking['id'], EmailLog.status == 'failed'))
            assert failed.body is None  # Queue must never silently retry without the files.
            failed_id = failed.id
        retry = client.post(f'/api/communications/failures/email/{failed_id}/retry')
        assert retry.status_code == 409
        assert 'reselect' in retry.json()['detail']
