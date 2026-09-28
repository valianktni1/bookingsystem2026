"""Editable final-timings wording and extra questions; calculation keys stay fixed."""
from copy import deepcopy
from datetime import date, time
from hashlib import sha256
import json
import re
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from .models import Brand, FormTemplate, FormSubmission

BUILTINS = [
 ('ceremony_time','Ceremony time',0),('ceremony_duration','Expected ceremony length (minutes)',0),('ceremony_venue','Ceremony venue and full address',0),('reception_same','Is the reception at the same venue?',0),('reception_venue','Reception venue and full address',0),
 ('prep_photos','Would you like preparation photographs?',1),('prep_person','Who will I photograph getting ready?',1),('prep_venue','Preparation venue and full address',1),('travel_minutes','Travel time from preparations to ceremony (minutes)',1),('start_choice','Preferred start',1),('requested_start','Earlier start requested',1),('prep_notes','Preparation notes',1),('second_prep','Second preparation location or person',1),
 ('group_photo_time','Group photographs',2),('meal_time','Wedding breakfast / meal',2),('speeches_time','Speeches',2),('speeches_position','When are the speeches?',2),('evening_time','Evening guests arrive',2),('cake_time','Cake cutting',2),('first_dance_time','First dance',2),('later_event','Is there an essential photograph after the first dance?',2),('later_event_name','What is the later event?',2),('later_event_time','Later event time',2),('extra_stops','Extra venues, stops or travel during the day',2),
 ('day_contact','Wedding-day contact name',3),('day_mobile','Wedding-day mobile',3),('coordinator','Coordinator / venue contact',3),('group_count','Approximate number of formal group photographs',3),('important_notes','Important family details, surprises or anything I should know',3)]
OPTIONAL = {'prep_notes','second_prep','group_photo_time','meal_time','speeches_time','evening_time','cake_time','extra_stops','coordinator','important_notes'}
BASE_KEYS = {key for key,_,_ in BUILTINS}

class Question(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    key: str = Field(min_length=1,max_length=80)
    label: str = Field(min_length=1,max_length=240)
    help: str = Field(default='',max_length=1000)
    step: int = Field(ge=0,le=3)
    kind: str = 'builtin'
    enabled: bool = True
    required: bool = False
    options: list[str] = Field(default_factory=list,max_length=30)

class TimingsTemplateIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    heading: str = Field(min_length=1,max_length=160)
    introduction: str = Field(max_length=2000)
    submit_label: str = Field(min_length=1,max_length=80)
    fields: list[Question] = Field(min_length=29,max_length=59)
    expected_revision: str | None = None

def default_template():
    return {'heading':'Final Wedding Timings','introduction':'Complete the details below so I can prepare the day properly and check the expected photography coverage before our final telephone call.','submit_label':'Send my final timings','fields':[{'key':k,'label':l,'help':'','step':s,'kind':'builtin','enabled':True,'required':False,'options':[]} for k,l,s in BUILTINS]}

def revision(config):
    return sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]

def validate_template(payload):
    config=TimingsTemplateIn.model_validate(payload).model_dump(exclude={'expected_revision'})
    found=set()
    defaults={k:s for k,_,s in BUILTINS}
    for q in config['fields']:
        key=q['key']
        if key in found: raise ValueError('Each question must have a unique reference')
        found.add(key)
        if key in BASE_KEYS:
            if q['kind']!='builtin' or q['step']!=defaults[key] or q['options']:
                raise ValueError('Built-in question types, choices and sections must stay unchanged')
            if key not in OPTIONAL and (not q['enabled'] or q['required']):
                raise ValueError('Calculation and essential fields keep their existing required rules')
        else:
            if not re.fullmatch(r'extra_[a-z0-9_]{1,60}',key): raise ValueError('Invalid extra question reference')
            if q['kind'] not in {'text','textarea','select','yesno','date','time','number'}: raise ValueError('Choose a supported extra question type')
            if q['kind']=='select':
                q['options']=[x.strip() for x in q['options']]
                if not q['options'] or any(not x or len(x)>160 for x in q['options']) or len(set(q['options']))!=len(q['options']): raise ValueError('Choice questions need distinct, non-empty options')
            elif q['options']: raise ValueError('Only choice questions have editable options')
    if not BASE_KEYS<=found: raise ValueError('Built-in questions cannot be deleted; optional questions can be hidden')
    return config

def current_template(db):
    row=db.scalar(select(FormTemplate).where(FormTemplate.brand==Brand.WBM,FormTemplate.template_key=='final_timings'))
    return deepcopy(row.config) if row else default_template()

def effective_template(db, booking_id):
    row=db.scalar(select(FormSubmission).where(FormSubmission.booking_id==booking_id,FormSubmission.form_type=='final_timings'))
    # Already-submitted forms remain on their original version, including legacy forms.
    if row: return deepcopy((row.data or {}).get('_form_template') or default_template())
    return current_template(db)

def public_template(config):
    return {**deepcopy(config),'revision':revision(config),'optional_keys':sorted(OPTIONAL)}

def validate_extra_answers(config, raw):
    extra={}
    for q in config['fields']:
        key=q['key'];value=raw.get(key)
        if not q['enabled']: continue
        if key in {'prep_notes','second_prep'} and raw.get('prep_photos') in (False,'no','false'): continue
        if key in BASE_KEYS and key not in OPTIONAL: continue
        if q['required'] and (value is None or str(value).strip()==''): raise ValueError(f"Please complete {q['label']}")
        if key in BASE_KEYS: continue
        value='' if value is None else str(value).strip()
        if len(value)>5000: raise ValueError(f"{q['label']} is too long")
        if value:
            if q['kind']=='select' and value not in q['options']: raise ValueError(f"Please select a valid answer for {q['label']}")
            if q['kind']=='yesno' and value not in {'yes','no'}: raise ValueError(f"Please choose yes or no for {q['label']}")
            if q['kind']=='date': date.fromisoformat(value)
            if q['kind']=='time': time.fromisoformat(value)
            if q['kind']=='number' and not re.fullmatch(r'-?\d{1,12}(\.\d{1,6})?',value): raise ValueError(f"Please enter a number for {q['label']}")
        extra[key]=value
    return extra

def answer_snapshot(config, values):
    return [{'key':q['key'],'label':q['label'],'answer':values.get(q['key']),'step':q['step']} for q in config['fields'] if q['enabled']]
