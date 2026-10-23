"""Exercise production MIME/rendering without a mailbox or network connection."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_v873_email_layout import email_service as service, booking, profile, Brand

spec = importlib.util.spec_from_file_location('personal_defaults', Path(__file__).parents[1] / 'app/email_defaults.py')
defaults = importlib.util.module_from_spec(spec)
spec.loader.exec_module(defaults)


def cids(message):
    return {part['Content-ID'] for part in message.walk() if part['Content-ID']}


def test_followups_omit_awards_in_html_and_mime_but_manual_quotes_keep_them():
    for key in ('quote_followup_1', 'quote_followup_final', 'quote', 'manual_client_email', None):
        message = service.build_email_message(booking(), profile(), 'Hello', 'Hi', 'sender@example.com',
                    template_key=key, open_tracking_url='https://example.com/open.gif')
        markup = message.get_body(preferencelist=('html',)).get_content()
        awards = key not in service.QUOTE_FOLLOWUP_KEYS
        assert ('cid:weddings-by-mark-awards' in markup) == awards
        assert ('<weddings-by-mark-awards>' in cids(message)) == awards
        assert '<weddings-by-mark-logo>' in cids(message)
        assert 'https://example.com/open.gif' in markup
        assert message['Reply-To'] == 'mark@example.com'


def test_awards_setting_is_still_respected():
    p = profile()
    p.email_signature = {'show_awards': False}
    message = service.build_email_message(booking(), p, 'Hello', 'Hi', 'sender@example.com', template_key='manual_client_email')
    assert '<weddings-by-mark-awards>' not in cids(message)


def test_template_delivery_preview_and_retry_apply_same_awards_rule():
    for key in ('quote_followup_1', 'quote_followup_final', 'quote', 'manual_client_email'):
        template = SimpleNamespace(template_key=key, subject='Hello', body='Hi')
        awards = key not in service.QUOTE_FOLLOWUP_KEYS
        with patch.object(service, 'smtp_ready', return_value=True), \
             patch.object(service, 'smtp_credentials', return_value=('sender@example.com','unused')), \
             patch.object(service, 'render_template_content', return_value=('Hello','Hi')), \
             patch.object(service, 'template_values', return_value={}), \
             patch.object(service, 'send_email_message') as send:
            service.send_template_email(booking(),profile(),template,
                attachments=[{'content_type':'application/pdf','data':b'%PDF-test','filename':'invoice.pdf'}])
            message = send.call_args.args[0]
            assert ('<weddings-by-mark-awards>' in cids(message)) == awards
            assert any(part.get_filename()=='invoice.pdf' for part in message.walk())
            preview = service.preview_template_email(booking(),profile(),template)[2]
            assert ('cid:weddings-by-mark-awards' in preview) == awards
            service.send_rendered_email(booking(),profile(),'couple@example.com','Hello','Hi',template_key=key)
            assert ('<weddings-by-mark-awards>' in cids(send.call_args.args[0])) == awards


def test_upgrade_is_repeatable_and_preserves_custom_wording_and_inactive_status():
    for key, former in defaults.FORMER_EMAIL_DEFAULTS.items():
        template = SimpleNamespace(template_key=key,subject=former[0],body=former[1],is_active=False)
        assert defaults.upgrade_personal_email_defaults(template)
        assert (template.subject,template.body)==defaults.PERSONAL_EMAIL_DEFAULTS[key]
        assert not template.is_active
        assert not defaults.upgrade_personal_email_defaults(template)
        for field in ('subject','body'):
            custom = SimpleNamespace(template_key=key,subject=former[0],body=former[1])
            setattr(custom,field,getattr(custom,field)+' My personal edit')
            before=(custom.subject,custom.body)
            assert not defaults.upgrade_personal_email_defaults(custom)
            assert (custom.subject,custom.body)==before


def test_wbm_full_width_layout_is_inline_and_ivory_keeps_existing_layout():
    markup=service._email_html('Hi',booking(),profile())
    assert 'padding:22px 5px' in markup
    assert 'max-width:640px' not in markup
    assert '@media (min-width:641px)' not in markup
    ivory=service._email_html('Hi',booking(Brand.IVORY),profile(Brand.IVORY))
    assert 'max-width:640px' in ivory
    assert 'padding:32px 32px 28px' in ivory
