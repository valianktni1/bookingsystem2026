import os
from datetime import date, timedelta
import json

os.environ.setdefault('DATABASE_URL','sqlite://')
os.environ.setdefault('STORAGE_ROOT','tests/control-centre-storage')
os.environ.setdefault('CONTROL_CENTRE_ENABLED','false')

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main, control_centre
from app.config import get_settings
from app.database import Base, get_db
from app.models import Booking, Client, Brand, RecordKind, RecordStatus, Invoice, AuditLog


def fixture():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    app=FastAPI()
    control_centre.register_control_centre_routes(app,main.workflow_queues)
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_db]=session
    return engine,app


def add_booking(db,title,**kwargs):
    client=Client(first_name=title,last_name='Private',email='private-email@example.com',phone='private-phone')
    db.add(client);db.flush()
    row=Booking(title=title,client_id=client.id,brand=kwargs.pop('brand',Brand.WBM),
                kind=RecordKind.WEDDING,status=kwargs.pop('status',RecordStatus.ENQUIRY),
                event_date=date.today()+timedelta(days=14),venue_or_project='Example venue',
                notes='private-note',form_data={'private':'private-form'},**kwargs)
    db.add(row);db.flush()
    return row


def test_feed_requires_own_key_is_disabled_by_default_and_cannot_write(monkeypatch):
    engine,app=fixture()
    settings=get_settings()
    monkeypatch.setattr(settings,'control_centre_enabled',False)
    monkeypatch.setattr(settings,'control_centre_key','x'*48)
    with TestClient(app) as client:
        assert client.get('/api/integrations/control-centre/overview').status_code==503
        monkeypatch.setattr(settings,'control_centre_enabled',True)
        assert client.get('/api/integrations/control-centre/overview').status_code==401
        assert client.get('/api/integrations/control-centre/overview',cookies={'booking_session':'anything'}).status_code==401
        assert client.get('/api/integrations/control-centre/overview',headers={'X-Control-Centre-Key':'wrong'}).status_code==401
        response=client.get('/api/integrations/control-centre/overview',headers={'X-Control-Centre-Key':'x'*48})
        assert response.status_code==200
        assert response.headers['cache-control']=='private, no-store'
        assert response.json()['queues']['new_enquiries']['count']==0
        assert client.post('/api/integrations/control-centre/overview',headers={'X-Control-Centre-Key':'x'*48}).status_code==405
        assert TestClient(main.app).get('/api/bookings',headers={'X-Control-Centre-Key':'x'*48}).status_code==401
    engine.dispose()


def test_live_wbm_only_minimal_fields_payments_and_five_wedding_limit(monkeypatch):
    engine,app=fixture()
    with Session(engine) as db:
        for index in range(7):add_booking(db,f'Enquiry {index}')
        add_booking(db,'Quote waiting',status=RecordStatus.QUOTED)
        add_booking(db,'Test excluded',is_test=True)
        add_booking(db,'Archived excluded',archived_at=main.datetime.now(main.timezone.utc))
        add_booking(db,'Cancelled excluded',status=RecordStatus.CANCELLED)
        add_booking(db,'Ivory excluded',brand=Brand.IVORY)
        for index in range(6):add_booking(db,f'Confirmed {index}',status=RecordStatus.CONFIRMED)
        wedding=add_booking(db,'Overdue invoice',status=RecordStatus.CONFIRMED)
        db.add(Invoice(booking_id=wedding.id,brand=Brand.WBM,sequence=3001,number='WBM03001',
                       total=1200,paid=200,due_date=date.today()-timedelta(days=1),status='part_paid'))
        db.add(Invoice(booking_id=wedding.id,brand=Brand.WBM,sequence=3002,number='WBM03002',
                       total=500,paid=0,due_date=date.today()-timedelta(days=1),status='void'))
        db.commit()
        overview=control_centre.build_overview(db,main.workflow_queues)
        assert overview['queues']['new_enquiries']['count']==7
        assert len(overview['queues']['new_enquiries']['items'])==5
        assert overview['queues']['quotes_waiting']['count']==1
        assert overview['queues']['overdue_payments']['count']==1
        assert overview['queues']['overdue_payments']['total_amount_pence']==100000
        assert overview['queues']['forms_waiting']['count']==1
        assert len(overview['upcoming_weddings'])==5
        encoded=json.dumps(overview)
        for private in ('private-email','private-phone','private-note','private-form','Test excluded','Archived excluded','Cancelled excluded','Ivory excluded'):
            assert private not in encoded
        assert db.scalar(select(func.count()).select_from(AuditLog))==0
        assert db.get(Invoice,db.scalar(select(Invoice.id).where(Invoice.number=='WBM03001'))).paid==200
        assert all(item['path'].endswith('/overview') for item in overview['upcoming_weddings'])
    engine.dispose()


def test_queues_use_uk_business_date_for_payment_boundary(monkeypatch):
    engine,app=fixture()
    tomorrow=date.today()+timedelta(days=1)
    monkeypatch.setattr(main,'business_today',lambda:tomorrow)
    monkeypatch.setattr(control_centre,'business_today',lambda:tomorrow)
    with Session(engine) as db:
        wedding=add_booking(db,'Boundary',status=RecordStatus.CONFIRMED)
        db.add(Invoice(booking_id=wedding.id,brand=Brand.WBM,sequence=3100,number='WBM03100',
                       total=100,paid=0,due_date=date.today(),status='unpaid'))
        db.commit()
        data=control_centre.build_overview(db,main.workflow_queues)
        assert data['queues']['overdue_payments']['count']==1
        assert data['business_date']==tomorrow.isoformat()
    engine.dispose()
