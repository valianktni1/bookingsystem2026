import os,json
from copy import deepcopy
from pathlib import Path
from datetime import date,timedelta
os.environ.update(DATABASE_URL='sqlite:////tmp/wbm-v865.db',STORAGE_ROOT='/tmp/wbm-v865-storage',COOKIE_SECURE='false',ADMIN_EMAIL='mark@example.com',ADMIN_PASSWORD='SecureTestPassword!123',SESSION_SECRET='v865-local-test-session-secret-123456',REMINDERS_ENABLED='false')
import fitz
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.database import engine,SessionLocal
from app.models import FormSubmission,Booking,EmailLog
from app.timings_forms import default_template,validate_template,revision

ANSWERS={'ceremony_time':'13:00','ceremony_duration':45,'ceremony_venue':'Test Hall','reception_same':True,'prep_photos':False,'travel_minutes':0,'start_choice':'normal','first_dance_time':'19:30','later_event':False,'day_contact':'Alex Example','day_mobile':'07700900123','group_count':'1-5'}
def create(client,title):
 r=client.post('/api/bookings',json={'brand':'wbm','kind':'wedding','status':'confirmed','title':title,'client':{'first_name':'Alex','last_name':'Example','email':'alex@example.com'},'event_date':(date.today()+timedelta(days=10)).isoformat(),'venue_or_project':'Test Hall','package_name':'Silver Package 2'});assert r.status_code==201,r.text
 bid=r.json()['id'];p=client.post(f'/api/bookings/{bid}/portal',json={'expires_days':365});assert p.status_code==201,p.text
 return bid,p.json()['url'].split('/client/')[1]
def save(client,config):
 payload={k:config[k] for k in ['heading','introduction','submit_label','fields']};payload['expected_revision']=config['revision'];return client.put('/api/forms/final-timings',json=payload)
def submit(client,token,answers):return client.post(f'/api/client/{token}/forms',json={'form_type':'final_timings','data':answers})
def test_editor_lifecycle_and_preservation():
 engine.dispose();Path('/tmp/wbm-v865.db').unlink(missing_ok=True)
 with TestClient(app) as client:
  assert client.get('/api/forms/final-timings').status_code==401
  assert client.put('/api/forms/final-timings',json={}).status_code==401
  assert client.post('/api/auth/login',json={'email':'mark@example.com','password':'SecureTestPassword!123'}).status_code==200
  original=client.get('/api/forms/final-timings').json();assert len(original['fields'])==29
  old,oldtoken=create(client,'Existing submitted couple');assert submit(client,oldtoken,ANSWERS).status_code==200
  with SessionLocal() as db:
   oldrow=db.scalar(select(FormSubmission).where(FormSubmission.booking_id==old));oldrow.data={k:v for k,v in oldrow.data.items() if k not in {'_form_template','_answer_snapshot'}};db.commit();before=deepcopy(oldrow.data)
  new,token=create(client,'Editable timings test')
  config=deepcopy(original);config['heading']='Your wedding plans';config['fields'][0]['label']='What time does your ceremony begin?';config['fields'][0]['help']='Use the confirmed ceremony start.'
  next(q for q in config['fields'] if q['key']=='coordinator')['enabled']=False
  config['fields'].append({'key':'extra_music','label':'Your entrance song','help':'Song and artist, please.','step':3,'kind':'text','enabled':True,'required':True,'options':[]})
  # Publishing neither sends email nor rewrites any submitted answers.
  with SessionLocal() as db: emails_before=len(db.scalars(select(EmailLog)).all())
  result=save(client,config);assert result.status_code==200,result.text;config=result.json()
  with SessionLocal() as db:
   assert db.scalar(select(FormSubmission).where(FormSubmission.booking_id==old)).data==before
   assert len(db.scalars(select(EmailLog)).all())==emails_before
  public=client.get(f'/api/client/{token}').json();assert public['final_timings']['template']['heading']=='Your wedding plans'
  oldpublic=client.get(f'/api/client/{oldtoken}').json();assert oldpublic['final_timings']['template']['heading']=='Final Wedding Timings'
  assert submit(client,token,ANSWERS).status_code==409
  answers={**ANSWERS,'_template_revision':config['revision']}
  assert submit(client,token,answers).status_code==422
  answers['extra_music']='Lovely Day';answers['_form_template']={'heading':'Forged'}
  response=submit(client,token,answers);assert response.status_code==200,response.text
  public=client.get(f'/api/client/{token}').json();saved=next(s['data'] for s in public['submissions'] if s['form_type']=='final_timings')
  assert saved['extra_music']=='Lovely Day';assert saved['_form_template']['heading']=='Your wedding plans';assert saved['_calculation']==before['_calculation']
  assert next(x for x in saved['_answer_snapshot'] if x['key']=='ceremony_time')['label']=='What time does your ceremony begin?'
  pdf=client.get(f'/api/bookings/{new}/final-timings.pdf');assert pdf.status_code==200
  pdftext=''.join(p.get_text() for p in fitz.open(stream=pdf.content,filetype='pdf'));assert 'Your entrance song' in pdftext and 'Lovely Day' in pdftext
  Path('/tmp/v865-final-timings.pdf').write_bytes(pdf.content)
  config['fields'][-1]['label']='Different wording for new couples';updated=save(client,config);assert updated.status_code==200
  pinned=client.get(f'/api/client/{token}').json()['final_timings']['template'];assert pinned['fields'][-1]['label']=='Your entrance song'
  assert submit(client,token,{**answers,'extra_music':'Updated song'}).status_code==200
  assert save(client,config).status_code==409
  bad=updated.json();bad['fields'][0]['enabled']=False;assert save(client,bad).status_code==422
  assert client.get('/api/forms/final-timings').json()['fields'][0]['enabled'] is True
  # Imported submitted forms stay on their own version; no original is rewritten.
  with SessionLocal() as db:
   booking=db.get(Booking,old);booking.legacy_source='studio_ninja';db.commit()
  assert client.get(f'/api/bookings/{old}/portal').json()['final_timings']['template']['heading']=='Final Wedding Timings'
  fresh,freshtoken=create(client,'Browser new couple')
  Path('/tmp/wbm-v865-fixture.json').write_text(json.dumps({'booking':new,'token':token,'fresh':fresh,'fresh_token':freshtoken}))
