from tests.test_v834_invoice_amendments import reset_database, create_accepted_invoice
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient
from app.main import app
from app import growth_integration as integration
from app.database import SessionLocal
from app.models import Booking, DateBlock, RecordStatus, PackageOption, Brand
from sqlalchemy import select


def test_private_range_protects_confirmed_archived_and_holidays(monkeypatch):
    reset_database()
    key='availability-private-test-key'
    monkeypatch.setattr(integration.settings,'growth_integration_enabled',True)
    monkeypatch.setattr(integration.settings,'growth_integration_key',key)
    start=datetime.now(ZoneInfo('Europe/London')).date()+timedelta(days=2)
    end=start+timedelta(days=5)
    with TestClient(app) as client:
        booking_id,_,_=create_accepted_invoice(legacy=True)
        with SessionLocal() as db:
            booking=db.get(Booking,booking_id)
            booking.event_date=start
            booking.archived_at=datetime.now(timezone.utc)
            db.add(DateBlock(start_date=start+timedelta(days=1),end_date=start+timedelta(days=2),label='Private holiday'))
            db.add(DateBlock(start_date=start+timedelta(days=3),end_date=start+timedelta(days=3),deleted_at=datetime.now(timezone.utc)))
            package=db.scalar(select(PackageOption).where(PackageOption.brand==Brand.WBM))
            package.price=1350
            package.name='Current package'
            db.commit()
        url=f'/api/integrations/growth/availability?start={start}&end={end}'
        assert client.get(url).status_code==401
        result=client.get(url,headers={'X-Integration-Key':key})
        assert result.status_code==200,result.text
        data=result.json()
        assert [d['status'] for d in data['days']]==['booked','blocked','blocked','available','available','available']
        assert 'Private holiday' not in result.text and 'Sophie' not in result.text
        assert any(p['name']=='Current package' and p['price']=='1350.00' for p in data['packages'])
        for changes in [{'is_test':True},{'is_test':False,'status':RecordStatus.CANCELLED},{'status':RecordStatus.QUOTED}]:
            with SessionLocal() as db:
                booking=db.get(Booking,booking_id)
                for k,v in changes.items():setattr(booking,k,v)
                db.commit()
            assert client.get(url,headers={'X-Integration-Key':key}).json()['days'][0]['status']=='available'
        long=f'/api/integrations/growth/availability?start={start}&end={start+timedelta(days=732)}'
        assert client.get(long,headers={'X-Integration-Key':key}).status_code==422
        monkeypatch.setattr(integration.settings,'growth_integration_enabled',False)
        assert client.get(url,headers={'X-Integration-Key':key}).status_code==503
