from tests.test_v834_invoice_amendments import reset_database,create_accepted_invoice
from datetime import date,datetime,timedelta,timezone
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import growth_integration as integration
from app.models import Booking,RecordStatus,EmailLog,Quote
from sqlalchemy import select


def test_year_counts_ignore_sync_cutoff_and_include_archived_bookings(monkeypatch):
    reset_database()
    monkeypatch.setattr(integration.settings,'growth_integration_enabled',True)
    monkeypatch.setattr(integration.settings,'growth_integration_key','test-key')
    monkeypatch.setattr(integration.settings,'growth_sync_from_date',date(2099,1,1))
    with TestClient(app) as client:
        bid,_,_=create_accepted_invoice(legacy=True)
        with SessionLocal() as db:
            b=db.get(Booking,bid);b.event_date=date(2027,8,21);b.archived_at=datetime.now(timezone.utc);b.quoted_total=1350;db.commit()
        url='/api/integrations/growth/planning?year=2027';headers={'X-Integration-Key':'test-key'}
        assert client.get(url).status_code==401
        result=client.get(url,headers=headers).json()
        assert result['bookings']==1 and result['booked_value']=='1350.00'
        assert result['months'][7]['bookings']==1
        assert 'Sophie' not in str(result)
        with SessionLocal() as db:
            db.get(Booking,bid).status=RecordStatus.CANCELLED;db.commit()
        assert client.get(url,headers=headers).json()['bookings']==0
        start=datetime.now(timezone.utc).date()+timedelta(days=1)
        response=client.get(f'/api/integrations/growth/availability?start={start}&end={start+timedelta(days=731)}',headers=headers)
        assert response.status_code==200 and len(response.json()['days'])==732
        assert client.get(f'/api/integrations/growth/availability?start={start}&end={start+timedelta(days=732)}',headers=headers).status_code==422


def test_first_quote_timestamp_survives_resends():
    reset_database()
    with TestClient(app):
        bid,_,_=create_accepted_invoice()
        with SessionLocal() as db:
            b=db.get(Booking,bid)
            for day in [3,10]:db.add(EmailLog(booking_id=bid,template_key='quote',recipient=b.client.email,subject='Quote',status='sent',sent_at=datetime(2026,8,day,tzinfo=timezone.utc)))
            q=db.scalar(select(Quote).where(Quote.booking_id==bid));q.accepted_at=datetime(2026,8,12,tzinfo=timezone.utc)
            b.deposit_paid_date=date(2026,8,14);db.commit()
            facts=integration.communication_facts(b)
            assert facts['first_quote_sent_at'].startswith('2026-08-03')
            assert facts['quote_sent_at'].startswith('2026-08-10')
            assert facts['quote_accepted_at'].startswith('2026-08-12')
            assert facts['deposit_paid_date']=='2026-08-14'


def test_planning_timestamps_keep_batched_evidence_queries():
    from sqlalchemy import event
    from sqlalchemy.orm import selectinload
    from app.database import engine
    reset_database()
    with TestClient(app):
        bid,_,_=create_accepted_invoice()
        with SessionLocal() as db:
            b=db.get(Booking,bid)
            db.add(EmailLog(booking_id=bid,template_key='quote',recipient=b.client.email,subject='Quote',status='sent',sent_at=datetime(2026,8,3,tzinfo=timezone.utc)))
            db.add(Booking(brand=b.brand,kind=b.kind,status=RecordStatus.ENQUIRY,title='Second couple',client_id=b.client_id,event_date=date(2027,9,1)))
            db.commit()
            bookings=list(db.scalars(select(Booking).options(selectinload(Booking.client),selectinload(Booking.quotes))))
            queries=[]
            def count(conn,cursor,statement,parameters,context,executemany):
                if statement.lstrip().upper().startswith('SELECT'):queries.append(statement)
            event.listen(engine,'before_cursor_execute',count)
            try:
                facts=integration._communication_fact_map(db,bookings)
                for row in bookings:integration.build_booking_payload(row,facts[row.id])
            finally:event.remove(engine,'before_cursor_execute',count)
            assert len(queries)==3,queries
            assert facts[bid]['first_quote_sent_at'].startswith('2026-08-03')
