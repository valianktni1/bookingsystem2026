"""Isolated Ivory API and numbering checks. No live clients or mail."""
from datetime import date
from decimal import Decimal
from uuid import uuid4
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
import fitz
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from app import main
from app.database import Base, get_db
from app.models import Admin, Booking, Brand, BusinessProfile, Client, Invoice, InvoiceCounter, Payment, RecordKind, RecordStatus
from app.security import current_admin
from app.ivory_quotes import IvoryOffer, STARTER
from app.services import next_invoice_number


@pytest.fixture
def ctx(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path / 'ivory.db'}")
    @event.listens_for(engine,"connect")
    def enable(dbapi,_):dbapi.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    sessions=sessionmaker(engine,expire_on_commit=False)
    def dep():
        with sessions() as db:yield db
    main.app.dependency_overrides[get_db]=dep
    main.app.dependency_overrides[current_admin]=lambda:Admin(email="admin@example.com")
    with sessions() as db:
        db.add_all([BusinessProfile(brand=Brand.WBM,display_name="Weddings By Mark",invoice_prefix="WBM"),
                    BusinessProfile(brand=Brand.IVORY,display_name="Ivory Digital",invoice_prefix="ID",bank_details={"account_name":"Example studio","sort_code":"00-00-00","account_number":"00000000"})]);db.commit()
    yield TestClient(main.app),sessions
    main.app.dependency_overrides.clear();engine.dispose()


def payload():
    import copy
    d=copy.deepcopy(STARTER);d["email"]="andy@example.com"
    return {"request_id":str(uuid4()),"details":d}


def test_starter_invoice_payment_number_and_snapshot(ctx):
    client,sessions=ctx
    assert client.get('/api/ivory-quotes').json()==[]
    draft=client.post('/api/ivory-quotes',json=payload())
    assert draft.status_code==201,draft.text
    row=draft.json();assert row['invoice'] is None
    base='/api/ivory-quotes/'+row['id']
    agreed=client.post(base+'/accept',json={"name":"Andy","confirmed":True,"note":"Changes agreed by phone."})
    assert agreed.status_code==200,agreed.text
    invoice=agreed.json()['invoice']
    assert invoice['number'].startswith('WBM') and invoice['total']==1649 and invoice['paid']==599.50 and invoice['balance']==1049.50
    assert client.post(base+'/accept',json={"name":"Andy","confirmed":True,"note":"Repeat"}).json()['invoice']['id']==invoice['id']
    with sessions() as db:
        [payment]=db.scalars(select(Payment)).all();assert payment.paid_date==date(2026,10,19) and payment.amount==Decimal('599.50')
        assert len(db.scalars(select(Invoice)).all())==1
        # A subsequent wedding invoice takes the next shared number.
        seq,num=next_invoice_number(db,Brand.WBM);assert int(num[3:])==int(invoice['number'][3:])+1
        assert db.get(Booking,row['booking_id']).brand==Brand.IVORY
        profile=db.scalar(select(BusinessProfile).where(BusinessProfile.brand==Brand.IVORY))
        profile.bank_details={"sort_code":"11-11-11","account_number":"11111111"};db.commit()
    pdf=client.get('/api/invoices/'+invoice['id']+'/pdf')
    assert pdf.status_code==200,pdf.text
    text='\n'.join(p.get_text() for p in fitz.open(stream=pdf.content, filetype='pdf'))
    assert '1,649.00' in text and '1,049.50' in text and '19 October 2026' in text
    assert '00-00-00' in text and '11-11-11' not in text
    assert 'Original website design and build' in text
    assert client.post(base+'/revise',json=payload()).status_code==409


def test_client_accepts_once_and_revision_invalidates_old_link(ctx):
    c,sessions=ctx
    p=payload();p['details']['opening_paid']='0';p['details']['opening_paid_date']=None
    row=c.post('/api/ivory-quotes',json=p).json();old='/api/ivory-quotes/'+row['id']
    link=c.post(old+'/share').json()['url'];token=link.rsplit('/',1)[1];public='/api/public/ivory-quotes/'+token
    assert c.get(public).status_code==200
    revised=payload();revised['details']['change_reason']='Agreed additional content';revised['details']['opening_paid']='0';revised['details']['opening_paid_date']=None
    change=c.post(old+'/revise',json=revised);assert change.status_code==201,change.text
    assert c.get(public).status_code==404
    current=change.json();assert current['revision']==2
    token=c.post('/api/ivory-quotes/'+current['id']+'/share').json()['url'].rsplit('/',1)[1]
    public='/api/public/ivory-quotes/'+token
    assert c.get(public+'/invoice.pdf').status_code==404
    auth=main.app.dependency_overrides.pop(current_admin)
    try:
        assert c.get('/api/ivory-quotes').status_code==401
        assert c.post(public+'/accept',json={'name':'Andy','confirmed':False}).status_code==422
        first=c.post(public+'/accept',json={'name':'Andy','confirmed':True});assert first.status_code==200,first.text
        second=c.post(public+'/accept',json={'name':'Andy','confirmed':True});assert second.json()==first.json()
        assert c.get(public+'/invoice.pdf').content.startswith(b'%PDF')
    finally:main.app.dependency_overrides[current_admin]=auth
    with sessions() as db:assert len(db.scalars(select(Invoice)).all())==1


def test_shared_allocator_handles_occupied_numbers_and_rollback(ctx):
    _,sessions=ctx
    with sessions() as db:
        client=Client(first_name='Example',email='example@example.com');db.add(client);db.flush()
        b=Booking(client_id=client.id,title='Example',brand=Brand.IVORY,kind=RecordKind.DIGITAL,status=RecordStatus.IN_PROGRESS);db.add(b);db.flush()
        db.add(Invoice(booking_id=b.id,brand=Brand.IVORY,sequence=21,number='WBM02777',total=1,paid=0,status='unpaid'));db.commit()
        assert next_invoice_number(db,Brand.IVORY)==(2778,'WBM02778');db.rollback()
        assert next_invoice_number(db,Brand.WBM)==(2778,'WBM02778')


def test_templates_and_monthly_not_added_to_invoice(ctx):
    c,sessions=ctx
    templates=c.get('/api/ivory-quotes/templates').json()
    assert c.put('/api/ivory-quotes/templates',json=templates).status_code==200
    p=payload();p['details']['lines'].append({'name':'Hosting','amount':'35.00','kind':'monthly','selected':True,'description':'Monthly from launch'})
    p['details']['lines'].append({'name':'Optional work','amount':'500.00','kind':'one_off','selected':False,'description':''})
    row=c.post('/api/ivory-quotes',json=p).json();assert row['total']==1649 and row['monthly']==35
    path='/api/ivory-quotes/'+row['id']
    # Revision doesn't issue an invoice or send any email.
    pdf=c.get(path+'/pdf');assert pdf.content.startswith(b'%PDF')
    accepted=c.post(path+'/accept',json={'name':'Andy','confirmed':True,'note':'Agreed'});assert accepted.status_code==200
    with sessions() as db:
        invoice=db.scalars(select(Invoice)).one();assert len(invoice.line_items)==3 and invoice.total==1649
    # Another invoice on the same project cannot reuse the opening payment.
    p['request_id']=str(uuid4());p['booking_id']=row['booking_id']
    assert c.post('/api/ivory-quotes',json=p).status_code==409
    p['request_id']=str(uuid4());p['details']['opening_paid']='0';p['details']['opening_paid_date']=None
    assert c.post('/api/ivory-quotes',json=p).status_code==201


def test_rejects_wedding_project_and_missing_bank(ctx):
    c,sessions=ctx
    with sessions() as db:
        customer=Client(first_name='Couple',email='couple@example.com');db.add(customer);db.flush()
        b=Booking(client_id=customer.id,title='Wedding',brand=Brand.WBM,kind=RecordKind.WEDDING,status=RecordStatus.ENQUIRY);db.add(b);db.flush();bid=b.id
        profile=db.scalar(select(BusinessProfile).where(BusinessProfile.brand==Brand.IVORY));profile.bank_details={};db.commit()
    p=payload();p['booking_id']=bid
    assert c.post('/api/ivory-quotes',json=p).status_code==422
    p.pop('booking_id');row=c.post('/api/ivory-quotes',json=p).json()
    assert c.post('/api/ivory-quotes/'+row['id']+'/accept',json={'name':'Andy','confirmed':True,'note':'Agreed'}).status_code==422
    with sessions() as db:assert not db.scalars(select(Invoice)).all()


def test_preview_does_not_allocate_invoice_or_counter(ctx):
    c,sessions=ctx
    row=c.post('/api/ivory-quotes',json=payload()).json()
    preview=c.get('/api/ivory-quotes/'+row['id']+'/invoice-preview.pdf')
    assert preview.content.startswith(b'%PDF')
    doc=fitz.open(stream=preview.content,filetype='pdf')
    text='\n'.join(p.get_text() for p in doc)
    assert 'INVOICE PREVIEW' in ' '.join(text.split()) and '1,049.50' in text
    with sessions() as db:
        assert not db.scalars(select(Invoice)).all()
        assert not db.scalars(select(InvoiceCounter)).all()
