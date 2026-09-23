from io import BytesIO
from pathlib import Path
from PIL import Image
from test_v852_email_signature import _booking, _profile
from app.email_service import build_email_message, email_signature_asset
from app.models import Brand
from app.config import get_settings


def test_wbm_email_embeds_opaque_logo_without_changing_original():
    profile = _profile()
    asset = email_signature_asset(profile, 'logo')
    before = asset['path'].read_bytes()
    message = build_email_message(_booking(), profile, 'Hello', 'Hi Sophie', 'mark@example.com')
    part = next(p for p in message.walk() if p['Content-ID'] == '<weddings-by-mark-logo>')
    image = Image.open(BytesIO(part.get_payload(decode=True)))
    assert image.mode == 'RGB'
    assert image.getpixel((0, 0)) == (248, 245, 239)
    assert image.getpixel((image.width-1, image.height-1)) == (248, 245, 239)
    assert min(image.convert('L').getdata()) < 30  # lettering is retained
    assert part.get_content_type() == 'image/png'
    assert part.get_payload(decode=True) == asset['data']  # preview and sent image agree
    assert asset['path'].read_bytes() == before
    awards = email_signature_asset(profile, 'awards')
    assert 'data' not in awards
    ivory = _profile(brand=Brand.IVORY)
    assert 'data' not in email_signature_asset(ivory, 'logo')


def test_custom_transparent_logo_gets_same_backing_and_hidden_logo_stays_hidden(tmp_path):
    settings = get_settings()
    old = settings.storage_root
    settings.storage_root = tmp_path
    try:
        path = tmp_path / 'custom.png'
        image = Image.new('RGBA', (80, 40), (0, 0, 0, 0))
        image.putpixel((40, 20), (0, 0, 0, 255)); image.save(path)
        before = path.read_bytes()
        profile = _profile(email_signature={'logo_storage_name': 'custom.png', 'show_logo': True})
        rendered = Image.open(BytesIO(email_signature_asset(profile, 'logo')['data']))
        assert rendered.mode == 'RGB'
        assert rendered.getpixel((56, 36)) == (0, 0, 0)
        assert rendered.getpixel((16, 16)) == (248, 245, 239)
        assert path.read_bytes() == before
        profile.email_signature = {'logo_storage_name':'custom.png','show_logo':False}
        assert email_signature_asset(profile, 'logo') is None
    finally:
        settings.storage_root = old
