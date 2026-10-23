from test_v852_email_signature import _booking, _profile
from app.email_service import build_email_message, _email_html
from app.models import Brand


def test_light_wbm_email_preserves_links_plain_text_and_logo():
    body = 'Hi Alex,\n\nYour wedding quote is ready.\n\n[VIEW YOUR QUOTE](https://example.com/client/test?tab=quote)\n\nMark'
    message = build_email_message(_booking(), _profile(), 'Your wedding quote', body, 'mark@example.com', open_tracking_url='https://example.com/open.gif')
    markup = message.get_body(preferencelist=('html',)).get_content()
    assert 'content="light dark"' in markup
    assert 'background:#ffffff;color:#45433e' in markup
    assert 'background:#242321' not in markup
    assert 'class="wbm-email-message" bgcolor="#ffffff"' in markup
    assert 'https://example.com/client/test?tab=quote' in markup
    assert 'https://example.com/open.gif' in markup
    assert 'VIEW YOUR QUOTE' in message.get_body(preferencelist=('plain',)).get_content()
    assert any(part['Content-ID'] == '<weddings-by-mark-logo>' for part in message.walk())
    booking = _booking()
    booking.brand = Brand.IVORY
    ivory = _email_html('Hello', booking, _profile(brand=Brand.IVORY))
    assert 'background:#242321;color:#ffffff' in ivory
    assert 'content="light dark"' not in ivory

