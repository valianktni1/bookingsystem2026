from io import BytesIO
from PIL import Image
from test_v873_email_layout import email_service as service, booking, profile


def test_new_shared_awards_image_is_under_129kb_and_embedded_as_jpeg():
    asset=service.email_signature_asset(profile(),'awards')
    assert asset['path'].name=='weddings-by-mark-awards.jpg'
    data=asset['path'].read_bytes()
    assert len(data)<=129000
    image=Image.open(BytesIO(data))
    assert image.format=='JPEG'
    assert image.size==(1100,733)
    for key in ('quote','manual_client_email'):
        message=service.build_email_message(booking(),profile(),'Hello','Hi','sender@example.com',template_key=key)
        part=next(p for p in message.walk() if p['Content-ID']=='<weddings-by-mark-awards>')
        assert part.get_content_type()=='image/jpeg'
        assert part.get_payload(decode=True)==data

