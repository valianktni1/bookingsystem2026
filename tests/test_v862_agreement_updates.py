"""Completed agreements leave the actionable dashboard without a manual review."""
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
os.environ.update(DATABASE_URL='sqlite:////tmp/wbm-v862.db', STORAGE_ROOT='/tmp/wbm-v862-storage', COOKIE_SECURE='false', ADMIN_EMAIL='mark@example.com', ADMIN_PASSWORD='SecureTestPassword!123', SESSION_SECRET='local-test-only-session-secret-123456', REMINDERS_ENABLED='false')
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.database import SessionLocal, engine
from app.models import ContractAcceptance, EmailLog


def test_agreement_completion_queue_lifecycle():
    engine.dispose()
    Path('/tmp/wbm-v862.db').unlink(missing_ok=True)
    with TestClient(app) as client:
        assert client.post('/api/auth/login', json={'email':'mark@example.com','password':'SecureTestPassword!123'}).status_code == 200
        response = client.post('/api/bookings', json={'brand':'wbm','kind':'wedding','status':'confirmed','title':'Agreement queue test','client':{'first_name':'Alex','last_name':'Example','email':'alex@example.com'},'event_date':'2027-05-15','venue_or_project':'Test Hall'})
        assert response.status_code == 201, response.text
        bid = response.json()['id']
        signed = datetime.now(timezone.utc) - timedelta(days=5)
        with SessionLocal() as db:
            contract = ContractAcceptance(booking_id=bid, contract_title='Wedding agreement', contract_version='test', contract_body='Saved agreement', accepted_name='Alex Example', accepted_email='alex@example.com', accepted_at=signed)
            db.add(contract); db.commit(); cid = contract.id
        def updates():
            response = client.get('/api/workflow-queues')
            assert response.status_code == 200, response.text
            return {r['update_type'] for r in response.json()['queues']['client_updates']}
        assert 'agreement' in updates()
        with SessionLocal() as db:
            c = db.get(ContractAcceptance, cid)
            c.supplier_signed_at = signed + timedelta(minutes=1)
            c.supplier_signed_name = 'Mark Powell'
            db.commit()
        assert 'agreement_confirmation_pending' in updates()  # no two-day expiry
        with SessionLocal() as db:
            db.add(EmailLog(booking_id=bid, template_key='contract_completed', recipient='alex@example.com', subject='Confirmation', status='sent', sent_at=signed-timedelta(days=1)))
            db.add(EmailLog(booking_id=bid, template_key='contract_completed', recipient='alex@example.com', subject='Confirmation', status='failed', sent_at=signed+timedelta(minutes=2)))
            db.commit()
        assert 'agreement_confirmation_pending' in updates()  # old success cannot clear new signatures
        with SessionLocal() as db:
            db.add(EmailLog(booking_id=bid, template_key='contract_completed', recipient='alex@example.com', subject='Confirmation', status='sent', sent_at=signed+timedelta(minutes=3)))
            db.commit()
        assert not {'agreement','agreement_completed','agreement_confirmation_pending'} & updates()
        assert not {'agreement','agreement_completed','agreement_confirmation_pending'} & updates()
        with SessionLocal() as db:
            assert len(db.scalars(select(EmailLog).where(EmailLog.booking_id==bid)).all()) == 3
            c = db.get(ContractAcceptance, cid)
            assert c.contract_body == 'Saved agreement' and c.supplier_signed_name == 'Mark Powell'
            # Imported contracts retain their exclusion even with no confirmation.
            c.is_legacy_import = True
            c.supplier_signed_at = None
            db.commit()
        assert not {'agreement','agreement_confirmation_pending'} & updates()
