"""PDF layout regression checks using saved invoice data, without a database."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace as Obj
import fitz
import pytest
from app.models import Brand
def invoice_pdf(*args, **kwargs):
    # Import after test collection so existing integration suites can configure
    # their isolated environment before the application's settings are loaded.
    from app.pdf import invoice_pdf as render
    return render(*args, **kwargs)



def sample_invoice(description, *, legacy=False):
    client = Obj(first_name="Alex", partner_name="Sam", last_name="Example", company_name=None, email='sample@example.com', phone=None, address=None)
    booking = Obj(brand=Brand.WBM, kind='wedding', legacy_source=None, client=client, title='Alex & Sam', package_name='Saved Gold Package',
                  venue_or_project='Sample Wedding Venue', deposit_amount=Decimal('100'),
                  event_date=date(2027, 6, 12))
    invoice = Obj(brand=Brand.WBM, number='WBM-SAMPLE', booking=booking, status='unpaid',
                  issue_date=date(2026, 9, 22), deposit_due_date=None,
                  due_date=date(2027, 4, 28), supply_date=booking.event_date,
                  description=description, total=Decimal('899'), paid=Decimal('100'),
                  line_items=[] if legacy else [{'name':'Saved Gold Package', 'description':description, 'total':899}],
                  payments=[], payment_schedule=[], notes=None)
    profile = Obj(display_name='Weddings By Mark', legal_name='Weddings By Mark', address=None,
                  phone=None, email='sample@example.com', website=None, bank_details={})
    return invoice, profile


@pytest.mark.parametrize('description', [
    'Coverage included\r\nCeremony photographs\r\nHighlight film',
    'Coverage included • Ceremony photographs • Highlight film',
    '<p>Coverage included</p><ul><li>Ceremony photographs</li><li>Highlight film</li></ul>',
])
@pytest.mark.parametrize('legacy', [False, True])
def test_saved_inclusions_have_distinct_baselines_and_values_are_unchanged(description, legacy):
    invoice, profile = sample_invoice(description, legacy=legacy)
    saved = deepcopy(invoice.line_items)
    doc = fitz.open(stream=invoice_pdf(invoice, profile), filetype='pdf')
    positions = [doc[0].search_for(text)[0].y0 for text in
                 ['Coverage included', 'Ceremony photographs', 'Highlight film']]
    assert positions[1] > positions[0] + 10
    assert positions[2] > positions[1] + 10
    assert '£799.00' in ''.join(page.get_text() for page in doc)
    assert invoice.line_items == saved
    assert invoice.description == description
    assert invoice.total == Decimal('899') and invoice.paid == Decimal('100')


def test_long_package_continues_without_losing_features_or_totals():
    invoice, profile = sample_invoice('\n'.join(f'Included service number {i:03d}' for i in range(85)))
    doc = fitz.open(stream=invoice_pdf(invoice, profile), filetype='pdf')
    assert len(doc) > 1
    text = ''.join(page.get_text() for page in doc)
    for i in range(85):
        assert text.count(f'Included service number {i:03d}') == 1
    assert 'TOTAL OUTSTANDING' in text and '£799.00' in text
    for page in doc:
        for word in page.get_text('words'):
            assert word[0] >= 0 and word[2] <= page.rect.width
            assert word[1] >= 0 and word[3] <= page.rect.height


def test_plain_sentences_and_punctuation_are_not_split_into_guessed_inclusions():
    from app.pdf import invoice_description_lines
    assert invoice_description_lines('Photo, video and album. Up to 8 hours; travel included.') == [
        'Photo, video and album. Up to 8 hours; travel included.']
