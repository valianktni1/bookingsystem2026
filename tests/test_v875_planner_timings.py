"""Two real apps, disposable databases, intercepted transport. No SMTP."""
import importlib.util,json,sys,time
from pathlib import Path
from datetime import date
from unittest.mock import Mock
import pytest
from sqlalchemy import select
from test_v871_planner_invitations import booking,configure,NOW
from app.database import SessionLocal
from app.models import Booking,FormSubmission,SystemSetting,Task,Brand,FormTemplate
from app import planner_integration as bridge,planner_timings as timings,main
from app.timings_forms import default_template

@pytest.fixture
def client(tmp_path,monkeypatch):
    import asyncio
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from fastapi.testclient import TestClient
    engine=create_engine('sqlite:///'+str(tmp_path/'booking.sqlite3'),connect_args={'check_same_thread':False},poolclass=NullPool)
    previous=SessionLocal.kw['bind'];SessionLocal.configure(bind=engine)
    monkeypatch.setattr(main,'engine',engine)
    monkeypatch.setattr(main.settings,'storage_root',tmp_path/'storage')
    monkeypatch.setattr(bridge,'utcnow',lambda:NOW)
    async def idle(): await asyncio.sleep(86400)
    monkeypatch.setattr(main,'planner_invitation_loop',idle)
    try:
        with TestClient(main.app) as c:
            assert c.post('/api/auth/login',json={'email':'mark@example.com','password':'SecureTestPassword!123'}).status_code==200
            yield c
    finally:
        SessionLocal.configure(bind=previous);engine.dispose()

@pytest.fixture
def planner(tmp_path,monkeypatch):
    root=Path(__file__).parents[2]/'weddingplannercouples/app'
    if not root.exists():pytest.skip('Check out weddingplannercouples beside this repository')
    spec=importlib.util.spec_from_file_location('_ivory_bridge_fixture',root/'__init__.py',submodule_search_locations=[str(root)])
    pkg=importlib.util.module_from_spec(spec);sys.modules[spec.name]=pkg;spec.loader.exec_module(pkg)
    core=importlib.import_module(spec.name+'.core')
    app=pkg.create_app({'TESTING':True,'DATA_DIR':str(tmp_path/'planner'),'BACKUP_DIR':str(tmp_path/'backups'),'SECURE_COOKIES':False})
    db=core.connect(app.config['DATABASE']);s=core.empty_state();s.update(names=['Example','Partner'],email='sophie@example.com',date='2027-06-19',ready=True,notes='PRIVATE DO NOT SHARE',budget=20000)
    s['day']['venue']='Example Hall, Example Street';s['groups']=[{'id':'g','title':'Family photo','minutes':2}]
    db.execute('INSERT INTO users(id,email,password,role,verified,created) VALUES(?,?,?,?,1,?)',('couple','sophie@example.com','not-used','couple',time.time()))
    db.execute('INSERT INTO weddings(id,state,access_until,created) VALUES(?,?,?,?)',('wedding-example',json.dumps(s),'2030-01-01',time.time()))
    db.execute('INSERT INTO members VALUES(?,?)',('wedding-example','couple'))
    key='wbm_planner_'+'x'*48
    for k,v in {'wbm_booking_enabled':True,'wbm_booking_key_hash':core.digest(key)}.items():db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(k,json.dumps(v)))
    db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)',(core.digest('fixture-session'),'couple','fixture-csrf',time.time()+3600,None,None));db.commit();db.close()
    browser=app.test_client();browser.set_cookie('ivory_session','fixture-session')
    def transport(config,method,path,payload=None):
        import httpx
        r=app.test_client().open(path,method=method,json=payload,headers={'Authorization':'Bearer '+key})
        return httpx.Response(r.status_code,json=r.get_json())
    monkeypatch.setattr(bridge,'call_planner',transport)
    notify=Mock(return_value={'sent':True});monkeypatch.setattr(main,'send_owner_notification_safely',notify)
    monkeypatch.setattr(main,'sync_booking_calendar_safely',lambda *_:{})
    return app,browser,{'X-CSRF-Token':'fixture-csrf'},core,notify

def enable():
    configure(enabled=False)
    with SessionLocal() as db:
        row=db.get(SystemSetting,bridge.KEY);row.value={**row.value,'timings_enabled':True};db.commit()

def check(bid,today=date(2027,5,20)):
    with SessionLocal() as db:return timings.hold_timing_invitation(db,db.get(Booking,bid),today)

def submit(c,h,**changes):
    v=c.get('/api/wbm-timings').json;assert v['linked']
    answers={**v['answers'],'prep_photos':False,'day_contact':'Example contact','day_mobile':'07700900111',**changes}
    return c.post('/api/wbm-timings',json={'answers':answers,'confirmed':True,'revision':v['revision'],'hub_revision':v['hub_revision']},headers=h)

def test_off_by_default(client,planner,monkeypatch):
    bid=booking();configure(enabled=False);spy=Mock();monkeypatch.setattr(bridge,'call_planner',spy)
    assert not check(bid);spy.assert_not_called();assert planner[1].get('/api/wbm-timings').json=={'linked':False}

def test_active_hold_and_exact_fallback(client,planner):
    bid=booking();enable();assert check(bid)
    assert check(bid,date(2027,5,28));assert not check(bid,date(2027,5,29))
    assert planner[1].get('/api/wbm-timings').json['linked']
    db=planner[3].connect(planner[0].config['DATABASE']);assert db.execute('SELECT count(*) FROM mail').fetchone()[0]==0
    assert json.loads(db.execute('SELECT state FROM weddings').fetchone()[0])['budget']==20000;db.close()

def test_login_only_date_mismatch_failure_import(client,planner,monkeypatch):
    bid=booking();enable();db=planner[3].connect(planner[0].config['DATABASE']);s=json.loads(db.execute('SELECT state FROM weddings').fetchone()[0]);s['day']=planner[3].empty_state()['day'];db.execute('UPDATE weddings SET state=?',(json.dumps(s),));db.commit();db.close()
    assert not check(bid)
    with SessionLocal() as db:b=db.get(Booking,bid);b.event_date=date(2027,6,20);db.commit()
    assert not check(bid)
    spy=Mock(side_effect=RuntimeError('offline'));monkeypatch.setattr(bridge,'call_planner',spy);assert not check(bid)
    with SessionLocal() as db:b=db.get(Booking,bid);b.legacy_source='studio_ninja';db.commit()
    spy.reset_mock();assert not check(bid);spy.assert_not_called()

def test_roundtrip_pdf_review_notification_and_replays(client,planner):
    bid=booking();enable();assert check(bid)
    _,c,h,_,notify=planner;r=submit(c,h);assert r.status_code==201,r.json
    assert submit(c,h).json['id']==r.json['id'];assert check(bid,date(2027,5,29))
    assert c.get('/api/wbm-timings').json['latest']['status']=='received'
    with SessionLocal() as db:
        row=db.scalar(select(FormSubmission).where(FormSubmission.booking_id==bid));assert row.submission_source=='ivory_planner';assert row.source_document_id;assert row.data['_calculation']['timeline']
        assert 'planner_group_1' in {x['key'] for x in row.data['_answer_snapshot']}
        receipt=db.scalar(select(timings.PlannerTimingReceipt));assert 'PRIVATE' not in json.dumps(receipt.snapshot);assert 'budget' not in receipt.snapshot
        assert db.scalar(select(Task).where(Task.booking_id==bid,Task.workflow_key=='wbm_review_final_timings')).completed is False
    assert notify.call_count==1;assert check(bid,date(2027,6,1));assert notify.call_count==1
    assert submit(c,h,day_contact='Updated contact').status_code==201
    with SessionLocal() as db:timings.check_booking(db,db.get(Booking,bid),bridge.connection(db))
    assert check(bid)
    with SessionLocal() as db:assert len(db.scalars(select(timings.PlannerTimingReceipt)).all())==2
    assert notify.call_count==2

def test_invalid_or_other_source_never_overwrites(client,planner):
    bid=booking();enable();check(bid);_,c,h,_,notify=planner
    assert submit(c,h,day_contact='').status_code==201;assert not check(bid)
    assert c.get('/api/wbm-timings').json['latest']['status']=='needs_attention'
    with SessionLocal() as db:
        assert db.scalar(select(FormSubmission).where(FormSubmission.booking_id==bid)) is None
        db.add(FormSubmission(booking_id=bid,form_type='final_timings',submission_source='client_portal',data={'original':'keep these answers'}));db.commit()
    assert submit(c,h).status_code==201;assert not check(bid)
    with SessionLocal() as db:assert db.scalar(select(FormSubmission).where(FormSubmission.booking_id==bid)).data=={'original':'keep these answers'}
    notify.assert_not_called()

def test_csrf_stale_preview_and_custom_questions(client,planner):
    bid=booking();enable();check(bid);app,c,h,core,notify=planner
    assert app.test_client().get('/api/wbm-timings').status_code==401
    assert c.post('/api/wbm-timings',json={}).status_code==403
    assert app.test_client().post('/api/integrations/wbm/timings/link',json={}).status_code==401
    v=c.get('/api/wbm-timings').json;db=core.connect(app.config['DATABASE']);db.execute('UPDATE weddings SET revision=revision+1');db.commit();db.close()
    assert c.post('/api/wbm-timings',json={'confirmed':True,'answers':v['answers'],'revision':v['revision'],'hub_revision':v['hub_revision']},headers=h).status_code==409
    with SessionLocal() as db:
        t=default_template();t['fields'].append({'key':'extra_example','label':'New required answer','help':'','step':3,'kind':'text','enabled':True,'required':True,'options':[]})
        f=db.scalar(select(FormTemplate).where(FormTemplate.template_key=='final_timings',FormTemplate.brand==Brand.WBM));
        if f:f.config=t
        else:db.add(FormTemplate(brand=Brand.WBM,template_key='final_timings',display_name='Final timings',config=t))
        db.commit()
    check(bid);assert submit(c,h).status_code==201;assert not check(bid)
    assert 'New required answer' in c.get('/api/wbm-timings').json['latest']['message']
    assert submit(c,h,extra_example='Confirmed').status_code==201;assert check(bid);notify.assert_called_once()

def test_real_worker_collects_updates_without_invitation_automation(client,planner,monkeypatch):
    from datetime import timedelta
    from test_v871_planner_invitations import NOW
    bid=booking();enable();bridge.run_planner_jobs()
    _,c,h,_,notify=planner;assert submit(c,h).status_code==201
    monkeypatch.setattr(bridge,'utcnow',lambda:NOW+timedelta(minutes=3));bridge.run_planner_jobs()
    with SessionLocal() as db:assert db.scalar(select(timings.PlannerTimingReceipt)) is not None
    assert c.get('/api/wbm-timings').json['latest']['status']=='received';notify.assert_called_once()

def test_reminder_runner_holds_only_until_deadline_and_fails_open(client,planner,monkeypatch):
    bid=booking();enable()
    monkeypatch.setattr(main,'_due_reminders',lambda db,b,today:[('check_in_30',date(2027,5,20))])
    attempt=Mock(return_value=True);monkeypatch.setattr(main,'_attempt_reminder',attempt)
    with SessionLocal() as db:main.run_due_reminders(db,today=date(2027,5,20))
    attempt.assert_not_called()
    with SessionLocal() as db:main.run_due_reminders(db,today=date(2027,5,29))
    assert attempt.call_count==1

def test_lost_ack_replays_without_second_alert_or_submission(client,planner,monkeypatch):
    bid=booking();enable();check(bid);_,c,h,_,notify=planner;submit(c,h)
    transport=bridge.call_planner
    def lose_ack(config,method,path,payload=None):
        if path.endswith('/ack'):raise RuntimeError('Response lost')
        return transport(config,method,path,payload)
    monkeypatch.setattr(bridge,'call_planner',lose_ack)
    with SessionLocal() as db:timings.check_booking(db,db.get(Booking,bid),bridge.connection(db))
    assert c.get('/api/wbm-timings').json['latest']['status']=='queued';assert notify.call_count==1
    monkeypatch.setattr(bridge,'call_planner',transport)
    with SessionLocal() as db:timings.check_booking(db,db.get(Booking,bid),bridge.connection(db))
    assert c.get('/api/wbm-timings').json['latest']['status']=='received';assert notify.call_count==1
    with SessionLocal() as db:assert len(db.scalars(select(timings.PlannerTimingReceipt)).all())==1

def test_opt_in_requires_matching_planner_capability(client,planner,monkeypatch):
    import httpx
    configure(enabled=False);transport=bridge.call_planner
    monkeypatch.setattr(bridge,'call_planner',Mock(return_value=httpx.Response(200,json={'ready':True})))
    assert client.put('/api/planner-invitations/settings',json={'enabled':False,'timings_enabled':True}).status_code==422
    assert not client.get('/api/planner-invitations/settings').json()['timings_enabled']
    monkeypatch.setattr(bridge,'call_planner',transport)
    assert client.put('/api/planner-invitations/settings',json={'enabled':False,'timings_enabled':True}).status_code==200
    assert client.get('/api/planner-invitations/settings').json()['timings_enabled']
    assert not client.get('/api/planner-invitations/settings').json()['enabled']
