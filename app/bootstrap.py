from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .content import WBM_CONTRACT_BODY, WBM_CONTRACT_TITLE, WBM_CONTRACT_VERSION
from .models import (AddOnOption, Admin, Booking, Brand, BusinessProfile, Client, ContractTemplate,
                     EmailTemplate, InvoiceCounter, PackageOption, RecordKind, RecordStatus)
from .security import hash_password
from .services import create_default_tasks


def bootstrap(db: Session) -> None:
    settings = get_settings()
    if not db.scalar(select(Admin).limit(1)):
        db.add(Admin(email=settings.admin_email.lower(), password_hash=hash_password(settings.admin_password)))

    profiles = {
        Brand.WBM: ("Weddings By Mark", "WBM", "mark@perfectweddingsbymark.uk", "perfectweddingsbymark.uk"),
        Brand.IVORY: ("Ivory Digital", "ID", "admin@ivorydigital.uk", "ivorydigital.uk"),
    }
    for brand, (name, prefix, email, website) in profiles.items():
        profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == brand))
        if not profile:
            db.add(BusinessProfile(brand=brand, display_name=name, invoice_prefix=prefix, email=email,
                                   phone="07712 117357", website=website,
                                   address="220 Ashurst Road, Manchester M22 5AX"))
        else:
            if not profile.email or (brand == Brand.IVORY and profile.email == "sales@ivorydigital.uk"):
                profile.email = email
            profile.phone = profile.phone or "07712 117357"
            profile.website = profile.website or website
            profile.address = profile.address or "220 Ashurst Road, Manchester M22 5AX"

    if not db.get(InvoiceCounter, "global"):
        db.add(InvoiceCounter(key="global", value=settings.invoice_start))
    db.commit()

    packages = [
        ("bronze", "Bronze Package 1 2026/27/28", 475, 100, """Half Day Photography

• Up to 4 hours coverage
• Ceremony photos
• Family and group photos
• Couple photos
• Candid photos
• Minimum of 300+ photos
• Online high-resolution gallery with download, sharing and printing rights
• Pre-wedding consultation
• All images fully edited and available within 5 working days

A £100 deposit secures your date."""),
        ("silver", "Silver Package 2 2026/27/28", 699, 100, """Full Day Photography

• Up to 8 hours coverage
• Guest photo gallery with QR code and upload link
• Ceremony photos
• Family and group photos
• Couple photos
• Candid photos
• Speeches
• Cutting of the cake
• First dance
• Minimum of 600+ photos
• Online high-resolution gallery with download, sharing and printing rights
• Pre-wedding consultation
• All images fully edited and available within 5 working days

A £100 deposit secures your date."""),
        ("gold", "Gold Package 3 2026/27/28", 899, 100, """Full Day Photography + Highlight Video + Drone

• Up to 8 hours coverage (extra hours can be added)
• 5–7 minute highlight film with background music of your choice
• Aerial photographs and video where legally allowed, safe and weather conditions permit
• Guest photo gallery with QR code and upload link
• Bridal preparation photos
• Ceremony photos
• Family and group photos
• Couple photos
• Candid photos
• Speeches
• Cutting of the cake
• First dance
• Minimum of 600+ photos
• Online high-resolution gallery with download, sharing and printing rights
• Pre-wedding consultation
• Images available within 5 working days; video within 7–10 working days

A £100 deposit secures your date."""),
        ("platinum", "Platinum Package 4 2026/27/28", 1299, 150, """Full Day Photography + Highlight Video + Ceremony & Speeches Video + Drone

• Up to 8 hours coverage (extra hours can be added)
• 1 photographer/highlight-video operator and 1 videographer for the full ceremony and speeches
• 5–7 minute highlight film with background music
• Full edited ceremony and speeches video
• Aerial photographs and video where legally allowed, safe and weather conditions permit
• Guest photo gallery with QR code and upload link
• Bridal preparation, ceremony, family/group, couple and candid photos
• Speeches, cutting of the cake and first dance
• Minimum of 600+ photos
• Online high-resolution gallery with download, sharing and printing rights
• Pre-wedding consultation
• Images available within 5 working days; video within 7–10 working days

A £150 deposit secures your date."""),
        ("ultimate", "Ultimate Package 2026/27/28", 1699, 150, """Full Day Photography + Highlight Video + Ceremony & Speeches Video + Drone

• Up to 8 hours coverage
• 1 photographer/highlight-video operator and 1 videographer for the full ceremony and speeches
• 5–7 minute highlight film with background music
• Full edited ceremony and speeches video
• Aerial photographs and video where legally allowed, safe and weather conditions permit
• Selfie booth for 2–3 hours
• 3 × 12-inch by 12-inch wedding albums
• Guest photo gallery with QR code and upload link
• Bridal preparation, ceremony, family/group, couple and candid photos
• Speeches, cutting of the cake and first dance
• Minimum of 600+ photos
• Online high-resolution gallery with download, sharing and printing rights
• Pre-wedding consultation
• Images available within 5 working days; video within 7–10 working days

A £150 deposit secures your date."""),
    ]
    for order, (code, name, price, deposit, description) in enumerate(packages, start=1):
        if not db.scalar(select(PackageOption).where(PackageOption.brand == Brand.WBM,
                                                      PackageOption.code == code)):
            db.add(PackageOption(brand=Brand.WBM, code=code, name=name, description=description,
                                 price=Decimal(price), deposit_amount=Decimal(deposit), display_order=order))

    addons = [
        ("album_offer", "Wedding album offer", 120, ["bronze", "silver", "gold", "platinum"],
         "Add a wedding album to your package for the offer price of £120 (normal price £200)."),
        ("photobooth", "Photobooth after the wedding breakfast", 249, ["silver", "gold", "platinum"],
         "2–3 hours from after the wedding breakfast until just after the first dance, with props, instant guest uploads and snap prints."),
        ("extra_hour_photo", "1 extra hour — 1 photographer", 85, ["silver", "gold"],
         "One additional hour of photography coverage for Silver or Gold."),
        ("extra_hour_photo_video", "1 extra hour — photographer & videographer", 155, ["platinum"],
         "One additional hour of photography and videography coverage for Platinum."),
        ("parent_albums", "2 × parent albums", 250, ["bronze", "silver", "gold", "platinum", "ultimate"],
         "Two additional albums for parents or relatives, matching the size and contents of the main album. Discount already applied."),
        ("speeches", "Speeches coverage", 55, ["bronze"],
         "Extend Bronze Package coverage until the speeches have finished."),
    ]
    for order, (code, name, price, eligible, description) in enumerate(addons, start=1):
        if not db.scalar(select(AddOnOption).where(AddOnOption.brand == Brand.WBM,
                                                   AddOnOption.code == code)):
            db.add(AddOnOption(brand=Brand.WBM, code=code, name=name, description=description,
                               price=Decimal(price), eligible_package_codes=eligible, display_order=order))
    db.commit()

    template_rows = {
        "quote": ("Quote email", "Your {business_name} quote", "Hi {client_first_name},\n\nThank you for getting in touch. Your quote for {package_name} is {quoted_total}.\n\nYou can review the details, complete your booking form and accept the agreement using your private link:\n{portal_url}\n\nIf you have any questions, just reply to this email.\n\nMark\n{business_name}\n{business_phone}"),
        "booking_link": ("Booking link", "Your private {business_name} booking link", "Hi {client_first_name},\n\nHere is your private booking link:\n{portal_url}\n\nPlease complete the booking form and read and accept the agreement. The date is secured once the booking fee and agreement are received.\n\nMark\n{business_name}"),
        "contract_reminder": ("Contract reminder", "A quick reminder about your booking agreement", "Hi {client_first_name},\n\nJust a quick reminder to complete your booking form and accept the agreement using your private link:\n{portal_url}\n\nGive me a shout if you need anything.\n\nMark"),
        "final_questionnaire": ("Final details questionnaire", "Final details for {event_date}", "Hi {client_first_name},\n\nYour wedding is getting closer, so it is time to collect the final timings and details. Please complete the final questionnaire here:\n{portal_url}\n\nMark\nWeddings By Mark"),
        "balance_due_14": ("Balance reminder - 14 days", "Balance reminder for {event_date}", "Hi {client_first_name},\n\nJust a friendly reminder that the remaining balance is due by {balance_due_date}. Your invoice contains the bank details and payment reference.\n\nMark\n{business_name}"),
        "balance_due_7": ("Balance reminder - 7 days", "Balance due soon for {event_date}", "Hi {client_first_name},\n\nA quick reminder that the remaining balance is now due. Please use the invoice number as your bank-transfer reference.\n\nMark\n{business_name}"),
        "payment_received": ("Payment received", "Payment received - thank you", "Hi {client_first_name},\n\nThank you, your payment has been received and your record is now confirmed.\n\nMark\n{business_name}"),
        "enquiry_received": ("Website enquiry acknowledgement", "Thank you for your Weddings By Mark enquiry", "Hi {client_first_name},\n\nThank you for getting in touch about your wedding on {event_date} at {venue_or_project}. I have received your enquiry and will come back to you as soon as I can.\n\nIn the meantime, if you need to add anything, simply reply to this email.\n\nMark\nWeddings By Mark\n{business_phone}"),
        "quote_accepted": ("Package accepted and invoice ready", "Your package is confirmed and your invoice is ready", "Hi {client_first_name},\n\nThank you for choosing your Weddings By Mark package. Your selection has been saved and your invoice is now available in your private booking portal:\n\n{portal_url}\n\nThe invoice contains the bank-transfer details and reference. You can use the same private link to complete your Wedding Booking Form, read and accept the agreement and return to your booking whenever needed.\n\nYour date is secured when the booking fee and agreement have been received.\n\nMark\nWeddings By Mark\n{business_phone}"),
    }
    for brand in (Brand.WBM, Brand.IVORY):
        for key, (name, subject, body) in template_rows.items():
            if brand == Brand.IVORY and key in ("final_questionnaire", "enquiry_received", "quote_accepted"):
                continue
            if not db.scalar(select(EmailTemplate).where(EmailTemplate.brand == brand, EmailTemplate.template_key == key)):
                db.add(EmailTemplate(brand=brand, template_key=key, display_name=name, subject=subject, body=body))

    db.flush()
    quote_template = db.scalar(select(EmailTemplate).where(EmailTemplate.brand == Brand.WBM,
                                                            EmailTemplate.template_key == "quote"))
    if (quote_template and quote_template.display_name == "Quote email"
            and quote_template.subject == "Your {business_name} quote"):
        quote_template.display_name = "Initial package quote"
        quote_template.subject = "Choose your Weddings By Mark package"
        quote_template.body = """Hi {client_first_name},

Thank you for your enquiry for {event_date} at {venue_or_project}.

I have put together your private Weddings By Mark quote. Use the secure link below to compare the available packages, choose any optional extras and see the complete total before accepting:

{portal_url}

Once you accept your selection, your invoice will be created automatically. Your date is secured when the booking fee and agreement have been received.

If you have any questions at all, simply reply to this email.

Mark
Weddings By Mark
{business_phone}"""

    digital_contract = """Ivory Digital Project Agreement\n\n1. Work begins when the agreed initial payment and this agreement have been received.\n\n2. The client will supply text, images, access details and approvals needed to complete the project.\n\n3. Timescales depend on receiving content and feedback promptly.\n\n4. The remaining balance is payable as shown on the invoice.\n\n5. Third-party costs, domains or services not included in the written quote require approval before purchase.\n\n6. The client confirms they have permission to use all supplied content."""
    contracts = {Brand.WBM: (WBM_CONTRACT_TITLE, WBM_CONTRACT_VERSION, WBM_CONTRACT_BODY),
                 Brand.IVORY: ("Ivory Digital Project Agreement", "Version 1.0", digital_contract)}
    for brand, (title, version, body) in contracts.items():
        existing_contract = db.scalar(select(ContractTemplate).where(ContractTemplate.brand == brand))
        if not existing_contract:
            db.add(ContractTemplate(brand=brand, title=title, version=version, body=body))
        elif brand == Brand.WBM and existing_contract.version == "Rev 1.3 - August 2024":
            existing_contract.title = title
            existing_contract.version = version
            existing_contract.body = body
    db.commit()

    if settings.seed_demo_data and not db.scalar(select(Booking).limit(1)):
        demo = [
            (Brand.WBM, RecordKind.WEDDING, "Sophie & James", "Sophie", "Taylor", "James Taylor", "sophie@example.co.uk", "Peckforton Castle", 1299),
            (Brand.WBM, RecordKind.WEDDING, "Lucy & Tom", "Lucy", "Moore", "Tom Moore", "lucy@example.co.uk", "Eaves Hall", 699),
            (Brand.IVORY, RecordKind.DIGITAL, "Broadfield Motors", "Chris", "", None, "chris@example.co.uk", "Website rebuild", 350),
        ]
        for index, row in enumerate(demo):
            brand, kind, title, first, last, partner, email, venue, total = row
            client = Client(first_name=first, last_name=last, partner_name=partner, company_name=title if kind == RecordKind.DIGITAL else None, email=email)
            db.add(client)
            db.flush()
            booking = Booking(brand=brand, kind=kind, status=RecordStatus.CONFIRMED, title=title, client_id=client.id, event_date=date.today()+timedelta(days=7+index*7), venue_or_project=venue, quoted_total=Decimal(total))
            db.add(booking)
            db.flush()
            create_default_tasks(db, booking.id, kind)
        db.commit()
