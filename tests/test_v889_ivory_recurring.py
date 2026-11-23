"""Recurring billing integration tests: isolated databases, synthetic customers, no mail."""
from datetime import date, timedelta
from decimal import Decimal

import fitz
import pytest
from sqlalchemy import select

from test_v888_ivory_quotes import ctx, payload
from app import ivory_quotes, ivory_recurring
from app.ivory_recurring import RecurringCycle, RecurringPlan, cycle_start, run_due_cycles
from app.models import Booking, Brand, BusinessProfile, EmailLog, Invoice, Payment, RecordKind
from app.security import current_admin
from app import main
from app.services import next_invoice_number


TODAY = date(2026, 11, 23)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(ivory_quotes, "business_today", lambda: TODAY)
    monkeypatch.setattr(ivory_recurring, "business_today", lambda: TODAY)


def recurring_payload(months=1, start=TODAY, *, setup=0, cycle_total=None):
    p = payload()
    p["details"].update(title="Website care & SEO", customer="Example Business", opening_paid="0",
                        opening_paid_date=None, lines=[{"name":"SEO", "description":"Agreed monthly search work", "amount":"60.00", "kind":"monthly", "selected":True}],
                        billing={"interval_months":months, "start_date":start.isoformat(), "due_days":0, "cycle_total":cycle_total})
    if setup:
        p["details"]["lines"].append({"name":"Website setup", "description":"One-off build", "amount":str(setup), "kind":"one_off", "selected":True})
    return p


def agree(client, data):
    res=client.post("/api/ivory-quotes", json=data)
    assert res.status_code == 201, res.text
    quote=res.json()
    accepted=client.post(f'/api/ivory-quotes/{quote["id"]}/accept',json={"name":"Example Customer","confirmed":True,"note":"Service and billing schedule agreed."})
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


@pytest.mark.parametrize("months,expected",[(1,60),(3,180),(6,360),(12,720)])
def test_frequency_total_service_period_and_shared_sequence(ctx, months, expected):
    c,sessions=ctx
    row=agree(c,recurring_payload(months))
    assert row["invoice"]["total"] == expected
    assert row["recurring"]["next_billing_date"] == cycle_start(TODAY,months,1).isoformat()
    with sessions() as db:
        invoice=db.scalars(select(Invoice)).one()
        assert invoice.brand == Brand.IVORY and invoice.paid == 0
        assert invoice.issue_date == TODAY and invoice.due_date == TODAY
        cycle=db.scalars(select(RecurringCycle)).one()
        assert cycle.period_start == TODAY
        assert cycle.period_end == cycle_start(TODAY,months,1)-timedelta(days=1)
        assert not list(db.scalars(select(Payment))) and not list(db.scalars(select(EmailLog)))
        _,number=next_invoice_number(db,Brand.WBM)
        assert int(number[3:])==int(invoice.number[3:])+1
    pdf=c.get(f'/api/invoices/{row["invoice"]["id"]}/pdf')
    text="\n".join(p.get_text() for p in fitz.open(stream=pdf.content,filetype="pdf"))
    assert "Service period" in text and "23 November 2026" in text and f'{expected:,.2f}' in text


def test_annual_upfront_price_override_and_no_monthly_duplicates(ctx):
    c,sessions=ctx
    row=agree(c,recurring_payload(12,cycle_total="650.00"))
    assert row["invoice"]["total"]==650
    assert run_due_cycles(today=date(2026,12,23),sessions=sessions)==0
    assert run_due_cycles(today=date(2027,5,23),sessions=sessions)==0
    assert run_due_cycles(today=date(2027,11,23),sessions=sessions)==1
    assert run_due_cycles(today=date(2027,11,23),sessions=sessions)==0
    with sessions() as db:
        assert len(list(db.scalars(select(Invoice))))==2
        assert all(x.total==650 and x.paid==0 for x in db.scalars(select(Invoice)))


def test_draft_share_preview_do_not_create_schedule_or_invoice(ctx):
    c,sessions=ctx
    row=c.post('/api/ivory-quotes',json=recurring_payload(3)).json()
    path='/api/ivory-quotes/'+row['id']
    assert c.get(path+'/invoice-preview.pdf').content.startswith(b'%PDF')
    quote=c.get(path+'/pdf')
    text='\n'.join(p.get_text() for p in fitz.open(stream=quote.content,filetype='pdf'))
    assert '180.00' in text and 'every 3 month(s)' in text
    assert c.post(path+'/share').status_code==200
    with sessions() as db:
        assert not list(db.scalars(select(RecurringPlan)))
        assert not list(db.scalars(select(Invoice)))


def test_acceptance_retries_create_one_plan_and_cycle(ctx):
    c,sessions=ctx
    row=agree(c,recurring_payload())
    for _ in range(2):
        repeat=c.post('/api/ivory-quotes/'+row['id']+'/accept',json={'name':'Example','confirmed':True,'note':'Retry'})
        assert repeat.json()['invoice']['id']==row['invoice']['id']
    assert run_due_cycles(today=TODAY,sessions=sessions)==0
    with sessions() as db:
        assert len(list(db.scalars(select(RecurringPlan))))==1
        assert len(list(db.scalars(select(RecurringCycle))))==1
        assert len(list(db.scalars(select(Invoice))))==1


@pytest.mark.parametrize("due_days", [0, 7])
def test_early_first_invoice_preserves_service_start_and_renewals(ctx, due_days):
    client, sessions = ctx
    service_start = date(2026, 11, 30)
    data = recurring_payload(start=service_start)
    data["details"]["billing"].update(issue_first_on_acceptance=True, due_days=due_days)
    row = agree(client, data)

    assert row["invoice"]["total"] == 60
    assert row["recurring"]["start_date"] == "2026-11-30"
    assert row["recurring"]["next_billing_date"] == "2026-12-30"
    assert run_due_cycles(today=service_start, sessions=sessions) == 0
    with sessions() as db:
        invoice = db.scalars(select(Invoice)).one()
        assert invoice.issue_date == TODAY
        assert invoice.supply_date == service_start
        assert invoice.due_date == service_start + timedelta(days=due_days)
        assert db.scalars(select(RecurringCycle)).one().period_end == date(2026, 12, 29)

    renewal = date(2026, 12, 30)
    assert run_due_cycles(today=renewal, sessions=sessions) == 1
    with sessions() as db:
        invoices = list(db.scalars(select(Invoice).order_by(Invoice.issue_date)))
        assert len(invoices) == 2
        assert invoices[1].issue_date == renewal
        assert invoices[1].due_date == renewal + timedelta(days=due_days)


def test_future_recurring_only_client_acceptance_returns_no_invoice_until_due(ctx):
    c,sessions=ctx
    p=recurring_payload(3,date(2027,1,31))
    row=c.post('/api/ivory-quotes',json=p).json()
    token=c.post('/api/ivory-quotes/'+row['id']+'/share').json()['url'].rsplit('/',1)[1]
    url='/api/public/ivory-quotes/'+token
    auth=main.app.dependency_overrides.pop(current_admin)
    try:
        assert c.get('/api/ivory-recurring').status_code==401
        assert c.post(url+'/accept',json={'name':'Example','confirmed':True}).json()['number'] is None
        assert c.post(url+'/accept',json={'name':'Example','confirmed':True}).status_code==200
        assert c.get(url).json()['recurring']['start_date']=='2027-01-31'
    finally: main.app.dependency_overrides[current_admin]=auth
    with sessions() as db: assert not list(db.scalars(select(Invoice)))
    assert run_due_cycles(today=date(2027,1,30),sessions=sessions)==0
    assert run_due_cycles(today=date(2027,1,31),sessions=sessions)==1
    assert c.get(url).json()['invoice']['number'].startswith('WBM')
    assert c.get(url+'/invoice.pdf').content.startswith(b'%PDF')


def test_oneoff_build_and_recurring_services_remain_separate(ctx):
    c,sessions=ctx
    row=agree(c,recurring_payload(3,setup=500))
    assert row['invoice']['total']==500
    with sessions() as db:
        assert sorted(x.total for x in db.scalars(select(Invoice)))==[180,500]
        assert not list(db.scalars(select(Payment)))


def test_pause_resume_skips_paused_periods_and_cancel_is_final(ctx,monkeypatch):
    c,sessions=ctx
    agree(c,recurring_payload())
    plan=c.get('/api/ivory-recurring').json()[0];url='/api/ivory-recurring/'+plan['id']+'/action'
    assert c.post(url,json={'action':'pause','expected_cycle':1}).status_code==200
    assert run_due_cycles(today=date(2027,2,23),sessions=sessions)==0
    monkeypatch.setattr(ivory_recurring,'business_today',lambda:date(2027,2,1))
    resume=c.post(url,json={'action':'resume','expected_cycle':1})
    assert resume.status_code==200 and resume.json()['next_billing_date']=='2027-02-23'
    assert c.post(url,json={'action':'generate','expected_cycle':1}).status_code==409
    assert run_due_cycles(today=date(2027,2,23),sessions=sessions)==1
    plan=c.get('/api/ivory-recurring').json()[0]
    assert c.post(url,json={'action':'cancel','expected_cycle':plan['next_cycle']}).status_code==200
    assert run_due_cycles(today=date(2027,3,23),sessions=sessions)==0
    assert c.post(url,json={'action':'resume','expected_cycle':plan['next_cycle']}).status_code==409


def test_edit_future_price_does_not_rewrite_issued_pdf_or_payment(ctx):
    c,sessions=ctx
    row=agree(c,recurring_payload())
    invoice_id=row['invoice']['id']
    original=c.get('/api/invoices/'+invoice_id+'/pdf').content
    plan=c.get('/api/ivory-recurring').json()[0]
    change=c.put('/api/ivory-recurring/'+plan['id'],json={'title':'Updated SEO','cycle_total':'75.00','description':'Updated agreed work','terms':'New agreed terms','expected_cycle':1,'confirmed':True})
    assert change.status_code==200,change.text
    assert run_due_cycles(today=date(2026,12,23),sessions=sessions)==1
    with sessions() as db:
        assert db.get(Invoice,invoice_id).total==60
        assert sorted(i.total for i in db.scalars(select(Invoice)))==[60,75]
    # ReportLab metadata timestamps can differ; compare the actual printed text.
    text=lambda pdf:'\n'.join(p.get_text() for p in fitz.open(stream=pdf,filetype='pdf'))
    assert text(original)==text(c.get('/api/invoices/'+invoice_id+'/pdf').content)


def test_missed_whole_period_requires_review_and_manual_generation(ctx, monkeypatch):
    c,sessions=ctx
    agree(c,recurring_payload())
    assert run_due_cycles(today=date(2027,2,1),sessions=sessions)==0
    plan=c.get('/api/ivory-recurring').json()[0]
    assert 'missed' in plan['last_error']
    monkeypatch.setattr(ivory_recurring,'business_today',lambda:date(2027,2,1))
    url='/api/ivory-recurring/'+plan['id']+'/action'
    generated=c.post(url,json={'action':'generate','expected_cycle':1})
    assert generated.status_code==200,generated.text
    # A stale double-click cannot generate the following period.
    assert c.post(url,json={'action':'generate','expected_cycle':1}).status_code==409
    with sessions() as db:
        assert len(list(db.scalars(select(Invoice))))==2


def test_archived_projects_are_not_billed_and_bad_plan_does_not_block_others(ctx):
    from app.models import now
    c,sessions=ctx
    first=agree(c,recurring_payload());agree(c,recurring_payload())
    with sessions() as db:
        db.get(Booking,first['booking_id']).archived_at=now();db.commit()
    assert run_due_cycles(today=date(2026,12,23),sessions=sessions)==1
    plans=c.get('/api/ivory-recurring').json()
    assert any(p['last_error'] for p in plans)


@pytest.mark.parametrize('anchor,months,index,expected',[
    (date(2027,1,31),1,1,date(2027,2,28)),(date(2027,1,31),1,2,date(2027,3,31)),
    (date(2028,2,29),12,1,date(2029,2,28)),(date(2028,2,29),12,4,date(2032,2,29)),
    (date(2026,11,30),3,1,date(2027,2,28)),(date(2026,11,30),6,1,date(2027,5,30))])
def test_month_end_and_leap_anchor_dates(anchor,months,index,expected):
    assert cycle_start(anchor,months,index)==expected


@pytest.mark.parametrize('change',[
    {'interval_months':2}, {'start_date':'2026-11-22'}, {'due_days':-1}, {'cycle_total':'0'}, {'cycle_total':'-5'}])
def test_invalid_billing_does_not_create_financial_records(ctx,change):
    c,sessions=ctx;p=recurring_payload();p['details']['billing'].update(change)
    assert c.post('/api/ivory-quotes',json=p).status_code==422
    with sessions() as db: assert not list(db.scalars(select(Invoice)))


def test_selected_monthly_rate_required_and_payment_cannot_be_assumed(ctx):
    c,_=ctx;p=recurring_payload();p['details']['lines'][0]['selected']=False
    assert c.post('/api/ivory-quotes',json=p).status_code==422
    p=recurring_payload();p['details']['opening_paid']='60';p['details']['opening_paid_date']=TODAY.isoformat()
    assert c.post('/api/ivory-quotes',json=p).status_code==422


def test_recurring_invoice_delete_requires_void_to_preserve_period(ctx):
    c,_=ctx;row=agree(c,recurring_payload());i=row['invoice']
    res=c.post('/api/invoices/'+i['id']+'/permanent-delete',json={'confirmation':'DELETE '+i['number'],'reason':'Synthetic mistaken period'})
    assert res.status_code==409 and 'recurring service period' in res.text


def test_failed_number_allocation_rolls_back_period_and_can_retry(ctx,monkeypatch):
    c,sessions=ctx;agree(c,recurring_payload())
    original=ivory_recurring.next_invoice_number
    def fail(*args):
        original(*args)
        raise RuntimeError('Synthetic allocation failure')
    monkeypatch.setattr(ivory_recurring,'next_invoice_number',fail)
    assert run_due_cycles(today=date(2026,12,23),sessions=sessions)==0
    with sessions() as db:
        assert len(list(db.scalars(select(Invoice))))==1
        assert db.scalars(select(RecurringPlan)).one().next_cycle==1
    monkeypatch.setattr(ivory_recurring,'next_invoice_number',original)
    assert run_due_cycles(today=date(2026,12,23),sessions=sessions)==1
    with sessions() as db:
        numbers=sorted(int(i.number[3:]) for i in db.scalars(select(Invoice)))
        assert numbers[1]==numbers[0]+1


def test_concurrent_scans_issue_a_period_once(ctx):
    from concurrent.futures import ThreadPoolExecutor
    c,sessions=ctx;agree(c,recurring_payload())
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:run_due_cycles(today=date(2026,12,23),sessions=sessions),range(2)))
    with sessions() as db:
        assert len(list(db.scalars(select(Invoice))))==2
        assert len(list(db.scalars(select(RecurringCycle))))==2
        assert db.scalars(select(RecurringPlan)).one().next_cycle==2


def test_complete_backup_includes_schedules_and_period_history(ctx):
    import json
    from app.backup import _database_export
    c,sessions=ctx;agree(c,recurring_payload(6))
    with sessions() as db:
        files,counts,schema=_database_export(db)
    assert counts['ivory_recurring_plans']==counts['ivory_recurring_cycles']==1
    plan=json.loads(files['database/ivory_recurring_plans.jsonl'])
    assert plan['interval_months']==6 and plan['next_cycle']==1
    assert schema['ivory_recurring_cycles']['foreign_keys']
