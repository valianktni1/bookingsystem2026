"""Bounded histories must contain the latest messages, with unchanged privacy scope."""
from datetime import datetime,timedelta,timezone
from sqlalchemy import delete,select
from test_v877_quote_bank_details import client
from test_v857_quote_templates import create_waiting_quote
from app.database import SessionLocal
from app.models import Booking,EmailLog,MailboxReply,Brand


def test_latest_sent_history_not_oldest_and_no_other_booking_mail(client,monkeypatch):
    monkeypatch.setattr('app.mail_routes.imap_ready',lambda *_:False)
    one,_=create_waiting_quote(client);two,_=create_waiting_quote(client)
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.execute(delete(EmailLog).where(EmailLog.booking_id.in_([one['id'],two['id']])))
        for booking in (one,two):
            for i in range(90):
                db.add(EmailLog(booking_id=booking['id'],template_key='manual_email',recipient='abdul-v8451@example.com',subject=f'Log {i:03d}',body='Example sent email',status='sent',sent_at=start+timedelta(minutes=i)))
                db.add(MailboxReply(booking_id=booking['id'],brand=Brand.WBM,recipient='abdul-v8451@example.com',subject=f'Reply {i:03d}',body='Example reply',status='sent',sent_at=start+timedelta(minutes=i),message_id=f'<{booking["id"]}-{i}@example.test>'))
        from app.owner_notifications import OWNER_NOTIFICATION_KEYS
        for recipient,key,status in [('different@example.com','manual_email','sent'),('abdul-v8451@example.com',next(iter(OWNER_NOTIFICATION_KEYS)),'sent'),('abdul-v8451@example.com','manual_email','failed')]:
            db.add(EmailLog(booking_id=one['id'],recipient=recipient,template_key=key,status=status,subject='NEVER EXPOSE',sent_at=start+timedelta(days=1000)))
        db.commit()
        other_ids={r.id for r in db.scalars(select(EmailLog).where(EmailLog.booking_id==two['id']))}|{r.id for r in db.scalars(select(MailboxReply).where(MailboxReply.booking_id==two['id']))}
    for limit in (10,60,100):
        response=client.get(f'/api/bookings/{one["id"]}/conversation?limit={limit}');assert response.status_code==200
        messages=response.json()['messages'];expected={f'{kind} {i:03d}' for kind in ('Log','Reply') for i in range(max(0,90-limit),90)}
        assert {m['subject'] for m in messages}==expected
        assert not any(m['id'].split(':')[-1] in other_ids for m in messages)
        assert messages==sorted(messages,key=lambda m:(m['date'],m['id']))
        assert client.get(f'/api/bookings/{one["id"]}/conversation?limit={limit}').json()['messages']==messages


def test_imported_record_history_is_read_only_and_still_scoped(client,monkeypatch):
    monkeypatch.setattr('app.mail_routes.imap_ready',lambda *_:False)
    item,_=create_waiting_quote(client)
    with SessionLocal() as db:
        record=db.get(Booking,item['id']);record.legacy_source='studio_ninja';record.automation_suppressed=True
        record.workflow_state={'protected_fixture':'unchanged'};db.commit()
        before=db.scalars(select(EmailLog).where(EmailLog.booking_id==item['id'])).all();before_ids=[row.id for row in before]
    assert client.get(f'/api/bookings/{item["id"]}/conversation?limit=10').status_code==200
    with SessionLocal() as db:
        record=db.get(Booking,item['id']);assert record.workflow_state=={'protected_fixture':'unchanged'} and record.automation_suppressed
        assert [row.id for row in db.scalars(select(EmailLog).where(EmailLog.booking_id==item['id']))]==before_ids
