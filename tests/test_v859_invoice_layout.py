"""Native PDF display must preserve importable values and stored records."""
from copy import deepcopy
from decimal import Decimal
from datetime import date
import fitz
import pytest
from test_v854_invoice_layout import sample_invoice


def render(invoice, profile, receipt=False):
    from app.pdf import invoice_pdf
    return fitz.open(stream=invoice_pdf(invoice, profile, receipt), filetype='pdf')


@pytest.mark.parametrize('paid,statuses', [(0,['Scheduled','Scheduled']), (50,['Part Paid','Scheduled']),
                                         (100,['Paid','Scheduled']), (200,['Paid','Part Paid']), (630,['Paid','Paid'])])
def test_payment_display_allocates_without_mutating(paid,statuses):
    from app.payment_display import allocated_schedule
    inv,profile=sample_invoice('Ceremony photos\nFamily and group photos')
    inv.total=Decimal('630');inv.paid=Decimal(paid)
    inv.payment_schedule=[{'label':'Booking fee','amount':100,'status':'scheduled','due_date':'2026-08-19'},
                          {'label':'Remaining balance','amount':530,'status':'scheduled','due_date':'2027-03-31'}]
    saved=deepcopy(inv.__dict__)
    rows=allocated_schedule(inv)
    assert [x['status'].replace('_',' ').title() for x in rows]==statuses
    text=''.join(p.get_text() for p in render(inv,profile))
    for status in statuses: assert status in text
    assert inv.payment_schedule==saved['payment_schedule']
    assert inv.total==saved['total'] and inv.paid==saved['paid']


def test_embedded_fonts_preserve_text_bank_and_values_on_one_page():
    inv,profile=sample_invoice('\n'.join(['Half Day Photography','Up to 4 hours coverage','Ceremony photos',
        'Family and group photos','Couple photos','Candid photos','Minimum of 300+ photos',
        'Online high-resolution gallery with download, sharing and printing rights','Pre-wedding consultation',
        'All images fully edited and available within 5 working days','A £100 deposit secures your date.']))
    inv.id='example';inv.total=Decimal('630');inv.line_items[0].update(name='Bronze Package',total=475)
    inv.line_items.append({'name':'2 extra hours — 1 Photographer','description':'2 Extra hours for 1 photographer','total':155})
    inv.booking.workflow_state={'invoice_bank_details':{'example':{'account_name':'Saved bank name','sort_code':'11-22-33','account_number':'12345678'}}}
    profile.bank_details={'account_name':'Changed account','account_number':'87654321'}
    inv.deposit_due_date=date(2026,8,19)
    inv.payment_schedule=[{'label':'Booking fee','amount':100,'status':'scheduled','due_date':'2026-08-19'},
                          {'label':'Remaining balance','amount':530,'status':'scheduled','due_date':'2027-03-31'}]
    original=deepcopy(inv.line_items)
    doc=render(inv,profile); assert len(doc)==1
    text=doc[0].get_text()
    for expected in ['Number','WBM-SAMPLE','Issue date','22 September 2026','BILL TO','Alex & Sam',
                     'Bronze Package','£475.00','£155.00','Subtotal','£630.00','Paid','£100.00',
                     'TOTAL OUTSTANDING','£530.00','Saved bank name','11-22-33','12345678']:
        assert expected in text
    assert '87654321' not in text
    assert inv.line_items==original
    assert any('DejaVuSans' in font[3] and font[1]=='ttf' for font in doc[0].get_fonts())


@pytest.mark.parametrize('source', ['invoice','booking'])
def test_protected_import_keeps_original_renderer(source):
    from app.pdf import _original_invoice_pdf
    inv,profile=sample_invoice('Saved original description')
    setattr(inv if source=='invoice' else inv.booking,'legacy_source','studio_ninja')
    current=render(inv,profile)
    old=fitz.open(stream=_original_invoice_pdf(inv,profile),filetype='pdf')
    assert [p.get_text() for p in current]==[p.get_text() for p in old]
    assert [p.get_pixmap().samples for p in current]==[p.get_pixmap().samples for p in old]


@pytest.mark.parametrize('status', ['void','cancelled'])
def test_closed_invoice_does_not_request_payment(status):
    inv,profile=sample_invoice('Saved service'); inv.status=status
    doc=render(inv,profile); text=''.join(p.get_text() for p in doc)
    assert '£0.00' in text and 'no' in text and 'payment is due' in text
    assert 'PAYMENT REFERENCE:' not in text and 'PAYMENT SCHEDULE' not in text


def test_receipt_and_discount_remain_extractable():
    inv,profile=sample_invoice('Saved service')
    inv.line_items.append({'name':'Private discount','total':-100})
    inv.total=Decimal('799')
    text=''.join(p.get_text() for p in render(inv,profile,True))
    assert 'RECEIPT' in text and '£-100.00' in text and '£699.00' in text
    assert 'PAYMENT REFERENCE:' not in text
