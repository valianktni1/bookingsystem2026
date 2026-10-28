import os
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

os.environ.update(DATABASE_URL='sqlite:////tmp/wbm-v880-fixtures.db',SESSION_SECRET='gallery-test-fixtures-only-longer-than-32')
from app.database import Base, SessionLocal, engine
from app.models import Booking, Client, Invoice, Quote, SystemSetting, Brand, RecordKind, RecordStatus
from app import gallery_integration as bridge

NOW=datetime(2026,10,28,12,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    monkeypatch.setattr(bridge,'utcnow',lambda:NOW)


def configure(**changes):
    s={'enabled':True,'enabled_since':(NOW-timedelta(hours=1)).isoformat(),
       'credential':bridge.encryptor().encrypt(b'wbm_gallery_fixture-only-key').decode(),
       'rules':{'package:package':bridge.Rule(configured=True,photography=True,full_day=True,album_mode='40').model_dump(),
                'addon:album':bridge.Rule(configured=True,album_mode='60').model_dump()},**changes}
    with SessionLocal() as db:
        row=db.get(SystemSetting,bridge.KEY)
        if row:row.value=s
        else:db.add(SystemSetting(key=bridge.KEY,value=s))
        db.commit()
    return s


def booking(paid=150,legacy=False,test=False,accepted_at=NOW,full_status=RecordStatus.CONFIRMED):
    with SessionLocal() as db:
        c=Client(first_name='John',partner_name='Nikki',email='john@example.com');db.add(c);db.flush()
        b=Booking(client_id=c.id,brand=Brand.WBM,kind=RecordKind.WEDDING,status=full_status,title='John & Nikki',event_date=date(2027,10,20),deposit_amount=150,legacy_source='studio_ninja' if legacy else None,is_test=test)
        db.add(b);db.flush();i=Invoice(booking_id=b.id,brand=Brand.WBM,sequence=1,number=b.id,total=699,paid=paid,status='part_paid',line_items=[{'type':'package','code':'bronze','total':699}]);db.add(i);db.flush()
        q=Quote(booking_id=b.id,status='accepted',package_id='package',invoice_id=i.id,deposit_amount=150,accepted_at=accepted_at);db.add(q);db.commit();return b.id


def result(bid):return httpx.Response(200,json={'booking_id':bid,'gallery_id':'fixture-gallery','status':'created','admin_url':'https://weddingsbymark.uk/admin/gallery/fixture-gallery','guest_url':'https://weddingsbymark.uk/s/johnnikkiguestuploads','guest_expires_at':'2027-10-23T00:01:00+00:00'})


def test_creation_exact_payload_and_no_repeated_creation(monkeypatch):
    configure();bid=booking();send=Mock(return_value=result(bid));monkeypatch.setattr(bridge,'call_gallery',send)
    bridge.run_jobs();assert send.call_count==1
    assert send.call_args.args[-1]=={'booking_id':bid,'first_name':'John','partner_first_name':'Nikki','email':'john@example.com','wedding_date':'2027-10-20','photography':True,'video':False,'full_day':True,'selfie_booth':False,'album_mode':'40'}
    bridge.run_jobs();assert send.call_count==1
    with SessionLocal() as db:assert db.get(bridge.GalleryProvision,bid).status=='created'


@pytest.mark.parametrize('change',[{'paid':50},{'legacy':True},{'test':True},{'accepted_at':NOW-timedelta(days=3)},{'full_status':RecordStatus.ENQUIRY}])
def test_no_partial_historical_imported_test_or_enquiry(monkeypatch,change):
    configure();bid=booking(**change);send=Mock();monkeypatch.setattr(bridge,'call_gallery',send);bridge.run_jobs();send.assert_not_called()
    with SessionLocal() as db:assert not db.get(bridge.GalleryProvision,bid)


def test_off_unconfigured_retry_and_network_replay(monkeypatch):
    configure(enabled=False);bid=booking();send=Mock();monkeypatch.setattr(bridge,'call_gallery',send);bridge.run_jobs();send.assert_not_called()
    configure(rules={});bridge.run_jobs();send.assert_not_called()
    with SessionLocal() as db:
        j=db.get(bridge.GalleryProvision,bid);assert j.status=='needs_attention';assert not j.payload
        j.status='pending';db.commit()
    configure();send.side_effect=httpx.ReadTimeout('simulated dropped response');bridge.run_jobs();assert send.call_count==1
    first=send.call_args.args[-1]
    with SessionLocal() as db:
        j=db.get(bridge.GalleryProvision,bid);assert j.status=='retry';j.next_at=NOW;db.commit()
    send.side_effect=None;send.return_value=result(bid);bridge.run_jobs();assert send.call_args.args[-1]==first


def test_invoice_upgrade_flags_manual_review_without_network_write(monkeypatch):
    configure();bid=booking();send=Mock(return_value=result(bid));monkeypatch.setattr(bridge,'call_gallery',send);bridge.run_jobs()
    with SessionLocal() as db:
        q=bridge.accepted(db,db.get(Booking,bid));i=db.get(Invoice,q.invoice_id);i.line_items=[*i.line_items,{'type':'addon','code':'album','total':150}];db.commit()
    bridge.run_jobs();assert send.call_count==1
    with SessionLocal() as db:assert db.get(bridge.GalleryProvision,bid).status=='needs_review'


def test_changed_request_after_lost_response_never_sent_again(monkeypatch):
    configure();bid=booking();send=Mock(side_effect=httpx.ReadTimeout('lost response'));monkeypatch.setattr(bridge,'call_gallery',send);bridge.run_jobs()
    with SessionLocal() as db:
        b=db.get(Booking,bid);b.client.partner_name='Changed';j=db.get(bridge.GalleryProvision,bid);j.next_at=NOW;db.commit()
    bridge.run_jobs();assert send.call_count==1
    with SessionLocal() as db:assert db.get(bridge.GalleryProvision,bid).status=='needs_attention'


def test_paid_album_upgrade_free_discount_album_and_bad_acknowledgements():
    s=configure();bid=booking()
    with SessionLocal() as db:
        b=db.get(Booking,bid);q=bridge.accepted(db,b);i=db.get(Invoice,q.invoice_id);i.line_items=[*i.line_items,{'type':'addon','code':'album','total':0}];db.commit()
        assert bridge.make_payload(db,b,s)['album_mode']=='60'
        i.line_items=[i.line_items[0],{'type':'discount','manual_amendment':True,'code':'manual_amendment_0','total':-100}];db.commit()
        assert bridge.make_payload(db,b,s)['album_mode']=='40'
        i.line_items=[i.line_items[0],{'type':'discount','discount':True,'code':'album','total':0}];db.commit()
        assert bridge.make_payload(db,b,s)['album_mode']=='60'
    with pytest.raises(RuntimeError):bridge.safe_result({'booking_id':bid,'gallery_id':'x','status':'created','admin_url':'https://evil.example/admin/gallery/x'},bid)


def test_admin_settings_key_secrecy_and_explicit_review(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app=FastAPI();bridge.register_routes(app)
    with TestClient(app) as c:
        assert c.get('/api/gallery-connection/settings').status_code==401
        app.dependency_overrides[bridge.current_admin]=lambda:None
        send=Mock(return_value=httpx.Response(200,json={'ready':True,'capabilities':{'gallery_provisioning':1}}))
        monkeypatch.setattr(bridge,'call_gallery',send)
        raw='wbm_gallery_'+('x'*50)
        assert c.put('/api/gallery-connection/settings',json={'enabled':False,'key':raw,'rules':{}}).status_code==200
        send.assert_not_called()
        body=c.get('/api/gallery-connection/settings').text;assert raw not in body;assert 'credential' not in body
        assert c.put('/api/gallery-connection/settings',json={'enabled':True,'rules':{}}).status_code==200
        assert send.call_args.args[1:] == ('GET','/api/integrations/wbm/status')
        configure();bid=booking();send.return_value=result(bid);bridge.run_jobs()
        with SessionLocal() as db:
            db.get(Booking,bid).client.partner_name='Updated';db.commit()
        bridge.run_jobs();before=send.call_count
        assert c.get('/api/bookings/'+bid+'/gallery').json()['status']=='needs_review'
        assert c.post('/api/gallery-connection/jobs/'+bid+'/reviewed').status_code==200
        bridge.run_jobs();assert send.call_count==before
        assert c.get('/api/bookings/'+bid+'/gallery').json()['status']=='created'
