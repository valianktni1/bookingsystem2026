from test_v825_quote_email_review import reset_database, login, app, TestClient
from app.bootstrap import bootstrap
from app.database import SessionLocal
from app.models import EmailTemplate, Brand
from app.email_defaults import PERSONAL_EMAIL_DEFAULTS, FORMER_EMAIL_DEFAULTS
from sqlalchemy import select


def test_fresh_install_and_existing_default_upgrade_preserve_edits():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            for key, desired in PERSONAL_EMAIL_DEFAULTS.items():
                template=db.scalar(select(EmailTemplate).where(EmailTemplate.brand==Brand.WBM,EmailTemplate.template_key==key))
                assert (template.subject,template.body)==desired
                template.subject,template.body=FORMER_EMAIL_DEFAULTS[key]
                if key=='quote_followup_final':
                    template.body+='\nMy own wording to keep.'
                if key=='quote_followup_1':
                    template.is_active=False
            db.commit()
            bootstrap(db)
            db.commit()
            for key, desired in PERSONAL_EMAIL_DEFAULTS.items():
                template=db.scalar(select(EmailTemplate).where(EmailTemplate.brand==Brand.WBM,EmailTemplate.template_key==key))
                if key=='quote_followup_final':
                    assert template.body.endswith('My own wording to keep.')
                else:
                    assert (template.subject,template.body)==desired
                if key=='quote_followup_1':
                    assert not template.is_active


def test_api_previews_show_awards_on_quote_but_not_followups():
    reset_database()
    with TestClient(app) as client:
        login(client)
        templates=client.get('/api/communications/templates').json()['templates']
        for key in PERSONAL_EMAIL_DEFAULTS:
            template=next(t for t in templates if t['brand']=='wbm' and t['template_key']==key)
            preview=client.get(f"/api/communications/templates/{template['id']}/preview")
            assert preview.status_code==200
            markup=preview.json()['html']
            assert ('/email-signature/assets/awards' in markup)==(key=='quote')
            assert 'padding:22px 5px' in markup
            assert 'SAMPLE-REF' not in markup
            assert '{payment_reference}' not in markup
