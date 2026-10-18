"""Email-only tests: no database, HTTP server, credentials or SMTP connection.

Isolate the module's unrelated persistence/settings dependencies. Render and
build actual production HTML/MIME with disposable booking/profile fixtures.
"""
import base64
import importlib.util
import re
import sys
import tempfile
import types
import unittest
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parents[1]


class Brand(str, Enum):
    WBM = 'wbm'
    IVORY = 'ivory'


def load_email_module():
    name = '_wbm_email_layout_test'
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / 'app')]
    sys.modules[name] = package
    settings = SimpleNamespace(storage_root=Path(tempfile.gettempdir()) / 'unused-wbm-email-layout')
    dependencies = {
        'config': {'get_settings': lambda: settings},
        'models': {'Brand': Brand, 'Booking': SimpleNamespace,
                   'BusinessProfile': SimpleNamespace, 'EmailTemplate': SimpleNamespace},
        'services': {'payment_reference': lambda booking, fallback: fallback},
        'quote_templates': {'booking_bank_details': lambda booking, profile: {}},
    }
    for suffix, attributes in dependencies.items():
        stub = types.ModuleType(name + '.' + suffix)
        stub.__dict__.update(attributes)
        sys.modules[stub.__name__] = stub
    spec = importlib.util.spec_from_file_location(name + '.email_service', ROOT / 'app/email_service.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


email_service = load_email_module()


def profile(brand=Brand.WBM):
    return SimpleNamespace(brand=brand, display_name='Weddings By Mark', phone='07712 117357',
                           email='mark@example.com', website='https://example.com',
                           email_signature={})


def booking(brand=Brand.WBM):
    return SimpleNamespace(brand=brand, client=SimpleNamespace(email='couple@example.com'))


BODY = ('Hi Dan,\nJust reaching out to you both to ask if you managed to speak with the venues '
        'and if you have both had any more thoughts on booking me for your big day.\n\n'
        'Look forward to hearing from you guys soon\n\nBest regards,\nMark\n\n'
        '[VIEW YOUR WEDDING ACCOUNT, INVOICES AND BOOKING DETAILS]'
        '(https://example.com/client/example?tab=invoices&ref=example)')


class EmailLayoutTests(unittest.TestCase):
    def test_mime_keeps_inline_artwork_plain_text_links_and_tracking(self):
        message = email_service.build_email_message(booking(), profile(), 'Hello', BODY,
                    'sender@example.com', open_tracking_url='https://example.com/open.gif')
        self.assertEqual(message['To'], 'couple@example.com')
        self.assertEqual(message['Reply-To'], 'mark@example.com')
        markup = message.get_body(preferencelist=('html',)).get_content()
        self.assertIn('https://example.com/open.gif', markup)
        self.assertIn('https://example.com/client/example?tab=invoices&amp;ref=example', markup)
        self.assertIn('VIEW YOUR WEDDING ACCOUNT', message.get_body(preferencelist=('plain',)).get_content())
        self.assertIn('https://example.com/client/example?tab=invoices&ref=example', message.get_body(preferencelist=('plain',)).get_content())
        refs = set(re.findall(r'src="cid:([^"]+)"', markup))
        parts = {p['Content-ID'].strip('<>'): p for p in message.walk() if p['Content-ID']}
        self.assertEqual(refs, {'weddings-by-mark-logo', 'weddings-by-mark-awards'})
        self.assertEqual(refs, set(parts))
        for part in parts.values():
            self.assertEqual(part.get_content_disposition(), 'inline')
            self.assertGreater(len(part.get_payload(decode=True)), 100)
        message.add_attachment(b'%PDF-example-only', maintype='application', subtype='pdf', filename='example.pdf')
        self.assertIsNotNone(message.get_body(preferencelist=('html',)))
        self.assertTrue(any(p.get_filename() == 'example.pdf' for p in message.walk()))

    def test_default_is_white_with_optional_explicit_dark_palette(self):
        markup = email_service._email_html(BODY, booking(), profile())
        self.assertIn('class="wbm-email-message" bgcolor="#ffffff"', markup)
        self.assertIn('content="light dark"', markup)
        self.assertNotIn('background:#242321', markup)
        self.assertIn('prefers-color-scheme:dark', markup)

    def test_html_escapes_untrusted_wording(self):
        markup = email_service._email_html('<script>alert(1)</script>', booking(), profile())
        self.assertNotIn('<script>', markup)
        self.assertIn('&lt;script&gt;', markup)

    def test_hidden_branding_and_custom_signature_remain_respected(self):
        p = profile()
        p.email_signature = {'show_logo': False, 'show_awards': False, 'text': 'Mark\nExample signature'}
        message = email_service.build_email_message(booking(), p, 'Hello', BODY, 'sender@example.com')
        self.assertFalse(any(part['Content-ID'] for part in message.walk()))
        markup = message.get_body(preferencelist=('html',)).get_content()
        self.assertIn('Mark<br>Example signature', markup)

    def test_ivory_keeps_its_existing_email_colours_and_spacing(self):
        markup = email_service._email_html('Hello', booking(Brand.IVORY), profile(Brand.IVORY))
        self.assertNotIn('content="light dark"', markup)
        self.assertIn('padding:24px 10px', markup)
        self.assertIn('padding:32px 32px 28px', markup)
        self.assertIn('background:#242321;color:#ffffff', markup)


def write_browser_fixtures():
    """Resolve CID parts only for local preview; delivery continues to use MIME."""
    message = email_service.build_email_message(booking(), profile(), 'Hello', BODY, 'sender@example.com')
    markup = message.get_body(preferencelist=('html',)).get_content()
    for part in message.walk():
        if part['Content-ID']:
            cid = part['Content-ID'].strip('<>')
            data = base64.b64encode(part.get_payload(decode=True)).decode('ascii')
            markup = markup.replace('cid:' + cid, 'data:' + part.get_content_type() + ';base64,' + data)
    target = Path(tempfile.gettempdir()) / 'wbm-v873-email.html'
    target.write_text(markup)


if __name__ == '__main__':
    write_browser_fixtures()
    unittest.main()
