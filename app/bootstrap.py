from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .content import WBM_CONTRACT_BODY, WBM_CONTRACT_TITLE, WBM_CONTRACT_VERSION
from .enquiry_forms import default_enquiry_form
from .booking_forms import default_booking_form
from .models import (AddOnOption, Admin, Booking, Brand, BusinessProfile, Client, ContractTemplate,
                     EmailTemplate, FormTemplate, Invoice, InvoiceCounter, PackageOption, Quote, RecordKind, RecordStatus,
                     SystemSetting, Task)
from .security import hash_password
from .services import create_default_tasks, sync_final_details_call_task


def bootstrap(db: Session) -> None:
    settings = get_settings()
    fresh_install = not db.scalar(select(Admin.id).limit(1))
    if fresh_install:
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

    enquiry_template = db.scalar(select(FormTemplate).where(
        FormTemplate.brand == Brand.WBM,
        FormTemplate.template_key == "website_enquiry",
    ))
    if not enquiry_template:
        db.add(FormTemplate(
            brand=Brand.WBM,
            template_key="website_enquiry",
            display_name="Website enquiry form",
            config=default_enquiry_form(),
            is_active=True,
        ))
        db.commit()

    booking_template = db.scalar(select(FormTemplate).where(
        FormTemplate.brand == Brand.WBM,
        FormTemplate.template_key == "wedding_booking_form",
    ))
    if not booking_template:
        db.add(FormTemplate(
            brand=Brand.WBM,
            template_key="wedding_booking_form",
            display_name="Wedding Booking Form",
            config=default_booking_form(),
            is_active=True,
        ))
    else:
        # Upgrade only the original V8.9.8 wording. Any wording Mark has
        # deliberately customised in the form editor remains untouched.
        booking_config = dict(booking_template.config or {})
        booking_wording_changed = False
        if booking_config.get("submit_label") == "Save Wedding Booking Form":
            booking_config["submit_label"] = "Submit Wedding Booking Form"
            booking_wording_changed = True
        if booking_config.get("success_message") == "Your Wedding Booking Form has been saved securely.":
            booking_config["success_message"] = (
                "Thank you. Your answers have been securely added to your wedding file "
                "and are now available to Mark."
            )
            booking_wording_changed = True
        if booking_wording_changed:
            booking_template.config = booking_config
    if not db.get(SystemSetting, "testing_mode"):
        db.add(SystemSetting(key="testing_mode", value={
            "enabled": False,
            "email": settings.admin_email.lower(),
        }))
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
    has_wbm_packages = db.scalar(select(PackageOption.id).where(PackageOption.brand == Brand.WBM).limit(1))
    if fresh_install and not has_wbm_packages:
        for order, (code, name, price, deposit, description) in enumerate(packages, start=1):
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
    has_wbm_addons = db.scalar(select(AddOnOption.id).where(AddOnOption.brand == Brand.WBM).limit(1))
    if fresh_install and not has_wbm_addons:
        for order, (code, name, price, eligible, description) in enumerate(addons, start=1):
            db.add(AddOnOption(brand=Brand.WBM, code=code, name=name, description=description,
                               price=Decimal(price), eligible_package_codes=eligible, display_order=order))
    db.commit()

    template_rows = {
        "quote": ("Quote email", "Your {business_name} quote", "Hi {client_first_name},\n\nThank you for getting in touch. Your quote for {package_name} is {quoted_total}.\n\nYou can review the details, complete your booking form and accept the agreement using your booking link:\n{portal_url}\n\nIf you have any questions, just reply to this email.\n\nMark\n{business_name}\n{business_phone}"),
        "booking_link": ("Booking link", "Your {business_name} booking link", "Hi {client_first_name},\n\nHere is your booking link:\n{portal_url}\n\nPlease complete the booking form and read and accept the agreement. Your date is secured as soon as I receive your first payment.\n\nMark\n{business_name}"),
        "contract_reminder": ("Contract reminder", "A quick reminder about your booking agreement", "Hi {client_first_name},\n\nJust a quick reminder to complete your booking form and accept the agreement using your wedding booking link:\n{portal_url}\n\nGive me a shout if you need anything.\n\nMark"),
        "quote_followup_1": ("Quote follow-up - next day", "Just checking you received your wedding quote", "Hi {client_first_name},\n\nI just wanted to check that the wedding quote I sent yesterday reached you safely. Emails occasionally find their way into spam or junk folders, so when you have a moment would you mind checking there if you cannot see it?\n\nHere is your wedding booking link again:\n{portal_url}\n\nThere is absolutely no pressure. If you have any questions or would like to talk through the packages, just reply to this email and I will be happy to help.\n\nThanks,\nMark\nWeddings By Mark"),
        "quote_followup_final": ("Quote follow-up - final check", "A final quick check about your wedding quote", "Hi {client_first_name},\n\nI just wanted to make one final quick check that you received your Weddings By Mark quote and were able to open it.\n\nYou can view it here whenever you are ready:\n{portal_url}\n\nIf your plans have changed, that is completely fine. If you would like any help choosing a package or have a question, simply reply and I will be happy to help.\n\nThanks,\nMark\nWeddings By Mark"),
        "deposit_due_1": ("Booking fee reminder", "A little reminder about your wedding booking fee", "Hi {client_first_name},\n\nThank you again for choosing Weddings By Mark. I just wanted to send a friendly reminder that the booking fee shown on your invoice is now due. Your date is secured as soon as I receive your first payment, even if you are paying the booking fee in more than one transfer.\n\nYou can view your invoice, bank details and payment reference here:\n{portal_url}\n\nIf the transfer is already on its way, please ignore this message and I will update your invoice as soon as it reaches me.\n\nThanks,\nMark\nWeddings By Mark"),
        "check_in_120": ("Wedding check-in - 120 days before", "Checking in with you both!", "Hi {client_first_name},\n\nI hope you are both well and that the wedding plans are coming along nicely. With your wedding getting closer, I just wanted to check in and see how everything is going.\n\nThere is nothing you need to complete today. If any plans, timings or contact details have changed, or if there is anything you would like to ask me, just reply to this email.\n\nI am really looking forward to your day.\n\nThanks,\nMark\nWeddings By Mark"),
        "balance_due_7": ("Final balance reminder - 7 days before", "A little reminder about your wedding balance", "Hi {client_first_name},\n\nI hope you are both well and the wedding plans are coming along nicely.\n\nJust a friendly reminder that the remaining balance for your wedding is due on {balance_due_date}. There is no need to do anything today; I simply like to give everyone a little notice.\n\nYou can view your invoice, bank details and payment reference here:\n{portal_url}\n\nIf you have already made the transfer, please ignore this email and I will update your booking as soon as it reaches me.\n\nThanks,\nMark\nWeddings By Mark"),
        "balance_due_10": ("Final balance reminder - 10 days before", "A little reminder about your wedding balance", "Hi {client_first_name},\n\nI hope you are both well and the wedding plans are coming along nicely.\n\nJust a friendly reminder that the remaining balance for your wedding is due on {balance_due_date}. There is no need to do anything today; I simply like to give everyone plenty of notice.\n\nYou can view your invoice, bank details and payment reference here:\n{portal_url}\n\nIf you have already made the transfer, please ignore this email and I will update your booking as soon as it reaches me.\n\nThanks,\nMark\nWeddings By Mark"),
        "balance_due_1": ("Final balance reminder - day before", "Your wedding balance is due tomorrow", "Hi {client_first_name},\n\nI hope you are both well. Just a quick friendly reminder that the remaining balance for your wedding is due tomorrow, {balance_due_date}.\n\nYou can view your invoice, bank details and payment reference here:\n{portal_url}\n\nIf the transfer is already on its way, please ignore this message and I will update your booking when it arrives.\n\nThanks,\nMark\nWeddings By Mark"),
        "balance_overdue_2": ("Final balance reminder - 2 days after", "A quick reminder about your wedding balance", "Hi {client_first_name},\n\nI hope you are both well. Just a little reminder that the remaining balance for your wedding was due on {balance_due_date}. I know how busy things can become in the run-up to a wedding, so this may simply have slipped your mind.\n\nYou can view your invoice, bank details and payment reference here:\n{portal_url}\n\nIf you have already made the transfer, please ignore this message and I will update your booking as soon as it reaches me. If you need to speak to me about anything, just reply to this email.\n\nThanks,\nMark\nWeddings By Mark"),
        "payment_received": ("Payment received", "Payment received - {payment_amount} - thank you", "Hi {client_first_name},\n\nThank you, I have received your payment of {payment_amount} on {payment_date}.\n\n{payment_status}.\n\nInvoice: {invoice_number}\nTotal paid so far: {total_paid}\nRemaining balance: {outstanding_balance}\nFinal balance due: {balance_due_date}\n\nYou can view the updated invoice, payment history and download your receipt in your wedding booking:\n{portal_url}\n\nThank you,\nMark\n{business_name}\n{business_phone}"),
        "enquiry_received": ("Website enquiry acknowledgement", "Thank you for your Weddings By Mark enquiry", "Hi {client_first_name},\n\nThank you for getting in touch about your wedding on {event_date} at {venue_or_project}. I have received your enquiry and will come back to you as soon as I can.\n\nYour secure wedding area has also been created. You can use this private link to return to your enquiry and, once prepared, view your package quote:\n{portal_url}\n\nIn the meantime, if you need to add anything, simply reply to this email.\n\nMark\nWeddings By Mark\n{business_phone}"),
        "new_enquiry_admin": ("New website enquiry - notify Mark", "New wedding enquiry - {couple_or_company} - {event_date}", "Hi Mark,\n\nA new wedding enquiry has just been submitted through your website.\n\nCouple: {couple_or_company}\nWedding date: {event_date}\nVenue/location: {venue_or_project}\nEmail: {client_email}\nPhone: {client_phone}\nPackage interest: {package_interest}\nSelfie booth interest: {selfie_booth_interest}\nSpecial offer code: {promo_code}\nHow they found you: {heard_about_us}\n\nTheir message:\n{enquiry_message}\n\nFun question answer:\n{fun_answer}\n\nOpen the booking system:\n{admin_url}\n\nYou can reply directly to this notification and it will go to the couple.\n\nWeddings By Mark Booking System"),
        "quote_accepted": ("Package accepted and invoice ready", "Your package is confirmed and your invoice is ready", "Hi {client_first_name},\n\nThank you for choosing your Weddings By Mark package. Your selection and any add-ons have been saved, and your invoice is now available in your wedding booking:\n\n{portal_url}\n\nYour booking fee of {deposit_amount} is due by {deposit_due_date}. The remaining balance is due by {balance_due_date}.\n\nPlease use the same secure link to complete your Wedding Booking Form/questionnaire and read and digitally sign your wedding contract. The invoice also contains the bank-transfer details and payment reference.\n\nYour date is secured as soon as I receive your first payment.\n\nMark\nWeddings By Mark\n{business_phone}"),
        "contract_completed": ("Agreement signed by both parties", "Your wedding agreement is now signed by both parties", "Hi {client_first_name},\n\nThank you for completing your wedding agreement.\n\nI am pleased to confirm that it has now been signed by you and countersigned by Mark Adam Powell on behalf of Weddings By Mark. A protected copy, including both names and the date and time of acceptance, is safely retained with your wedding booking.\n\nYou can view your completed agreement, invoice, payment history and all of your wedding details at any time using your secure booking link:\n\n{portal_url}\n\nThank you again for choosing Weddings By Mark. I am genuinely looking forward to being part of your special day.\n\nWarmest regards,\nMark\nWeddings By Mark\n{business_phone}"),
    }
    for brand in (Brand.WBM, Brand.IVORY):
        for key, (name, subject, body) in template_rows.items():
            if brand == Brand.IVORY and key in ("final_questionnaire", "enquiry_received", "quote_accepted",
                                                "new_enquiry_admin", "quote_followup_1",
                                                "quote_followup_final", "deposit_due_1", "check_in_120",
                                                "balance_due_7", "balance_due_10", "balance_due_1",
                                                "balance_overdue_2", "contract_completed"):
                continue
            # New system templates must also be added safely to an existing
            # installation. Existing edited templates are never overwritten.
            existing_template = db.scalar(select(EmailTemplate).where(
                EmailTemplate.brand == brand, EmailTemplate.template_key == key
            ))
            if not existing_template and (fresh_install or key == "contract_completed"):
                db.add(EmailTemplate(brand=brand, template_key=key, display_name=name, subject=subject, body=body))

    # There is one Wedding Booking Form/questionnaire only. Final details are
    # confirmed privately by Mark on the phone, so this old client form/email
    # must never be offered or sent again. The row is retained only so it can
    # be reviewed or deleted safely from the template manager.
    for obsolete in db.scalars(select(EmailTemplate).where(
            EmailTemplate.template_key == "final_questionnaire")).all():
        obsolete.is_active = False

    # Give every active upcoming wedding one private phone-call reminder.
    # This creates no portal form and sends no client email, including for
    # permanently suppressed Studio Ninja imports.
    for booking in db.scalars(select(Booking).where(
            Booking.brand == Brand.WBM,
            Booking.kind == RecordKind.WEDDING,
            Booking.archived_at.is_(None),
            Booking.status != RecordStatus.CANCELLED,
            Booking.event_date.is_not(None),
            Booking.event_date >= date.today())).all():
        sync_final_details_call_task(db, booking)
    for obsolete_task in db.scalars(select(Task).where(
            Task.title.ilike("%final%questionnaire%"))).all():
        obsolete_task.completed = True

    db.flush()
    quote_template = db.scalar(select(EmailTemplate).where(EmailTemplate.brand == Brand.WBM,
                                                            EmailTemplate.template_key == "quote"))
    if (quote_template and quote_template.display_name == "Quote email"
            and quote_template.subject == "Your {business_name} quote"):
        quote_template.display_name = "Initial package quote"
        quote_template.subject = "Choose your Weddings By Mark package"
        quote_template.body = """Hi {client_first_name},

Thank you for your enquiry for {event_date} at {venue_or_project}.

I have put together your Weddings By Mark quote. Use your wedding booking link below to compare the available packages, choose any optional extras and see the complete total before accepting:

{portal_url}

Once you accept your selection, your invoice will be created automatically. Your date is secured as soon as I receive your first payment.

If you have any questions at all, simply reply to this email.

Mark
Weddings By Mark
{business_phone}"""

    # Keep Mark's friendly, personal quote wording while preserving the safe
    # dynamic client/date/venue/link fields and business-settings bank details.
    if (quote_template and quote_template.display_name == "Initial package quote"
            and "I have put together your Weddings By Mark quote" in quote_template.body):
        quote_template.subject = "Your Weddings By Mark wedding quote"
        quote_template.body = """Hi {client_first_name},

Thank you for considering Weddings By Mark to capture your special day. I am thrilled to let you know that I still have your wedding date, {event_date}, available, and I would be honoured to be a part of it.

I understand that planning a wedding can feel overwhelming, but I am here to make the photography part as easy and stress-free as possible.

That is why I have put together a tailored quote specifically for your wedding at {venue_or_project}, with all of my available packages and optional extras. You can compare everything, make your choices and accept the quote through my online booking system.

[VIEW YOUR FULL QUOTE HERE]({portal_url})

If you are happy to go ahead, your chosen package and any extras will be saved and your itemised invoice will be created automatically. The booking fee shown for your chosen package is due within one day of accepting the quote, and your wedding date is secured as soon as I receive your first payment.

Why choose Weddings By Mark? Because I believe your wedding day is just as important to me as it is to you. I am committed to creating timeless images that will become cherished memories for years to come. With my experience, creativity and attention to detail, you can relax knowing that every precious moment will be captured beautifully.

I am more than happy to answer any questions or provide any additional information. Simply reply to this email or give me a call on {business_phone}, and I will be delighted to help.

Bank-transfer details
Account name: {bank_account_name}
Sort code: {bank_sort_code}
Account number: {bank_account_number}

Once you have accepted your quote, please use the invoice number shown in your wedding account as the payment reference.

Lastly, I would like to wish you both all the very best for your upcoming wedding day and your future together. I look forward to hearing from you and hopefully being a part of your special day.

Warmest wishes,
Mark
Weddings By Mark"""

    if (quote_template and quote_template.display_name == "Initial package quote"
            and "booking fee and agreement have been received" in quote_template.body):
        quote_template.body = quote_template.body.replace(
            "Your date is secured when the booking fee and agreement have been received.",
            "Your date is secured as soon as I receive your first payment.",
        )

    booking_link_template = db.scalar(select(EmailTemplate).where(
        EmailTemplate.brand == Brand.WBM,
        EmailTemplate.template_key == "booking_link",
    ))
    if (booking_link_template and booking_link_template.display_name == "Booking link"
            and "booking fee and agreement are received" in booking_link_template.body):
        booking_link_template.body = booking_link_template.body.replace(
            "The date is secured once the booking fee and agreement are received.",
            "Your date is secured as soon as I receive your first payment.",
        )

    # The real WBM schedule uses seven days, not the older 10/14-day reminders.
    for legacy in db.scalars(select(EmailTemplate).where(
            EmailTemplate.brand == Brand.WBM,
            EmailTemplate.template_key.in_(("balance_due_14", "balance_due_10")))).all():
        legacy.is_active = False
    due_seven = db.scalar(select(EmailTemplate).where(
        EmailTemplate.brand == Brand.WBM,
        EmailTemplate.template_key == "balance_due_7",
    ))
    if due_seven:
        due_seven.is_active = True
        if due_seven.display_name in ("Final balance reminder - 7 days before", "Balance due in 7 days"):
            due_seven.display_name = template_rows["balance_due_7"][0]
            due_seven.subject = template_rows["balance_due_7"][1]
            due_seven.body = template_rows["balance_due_7"][2]
    for row in db.scalars(select(EmailTemplate).where(EmailTemplate.brand == Brand.WBM)).all():
        row.subject = row.subject.replace("Your private Weddings By Mark booking link",
                                          "Your Weddings By Mark booking link")
        row.body = (row.body
                    .replace("your private Weddings By Mark quote", "your Weddings By Mark quote")
                    .replace("private Weddings By Mark quote", "Weddings By Mark quote")
                    .replace("your private booking portal", "your wedding booking")
                    .replace("the same private link", "the same wedding booking link")
                    .replace("your private booking link", "your wedding booking link")
                    .replace("private booking link", "wedding booking link")
                    .replace("your private link", "your wedding booking link"))
    accepted_template = db.scalar(select(EmailTemplate).where(
        EmailTemplate.brand == Brand.WBM, EmailTemplate.template_key == "quote_accepted"))
    if (accepted_template and accepted_template.display_name == "Package accepted and invoice ready"
            and "deposit_due_date" not in accepted_template.body):
        accepted_template.body = template_rows["quote_accepted"][2]
    if (accepted_template and accepted_template.display_name == "Package accepted and invoice ready"
            and "digitally sign your wedding contract" not in accepted_template.body):
        accepted_template.subject = template_rows["quote_accepted"][1]
        accepted_template.body = template_rows["quote_accepted"][2]

    enquiry_template = db.scalar(select(EmailTemplate).where(
        EmailTemplate.brand == Brand.WBM,
        EmailTemplate.template_key == "enquiry_received",
    ))
    if (enquiry_template and enquiry_template.display_name == "Website enquiry acknowledgement"
            and "{portal_url}" not in enquiry_template.body):
        enquiry_template.subject = template_rows["enquiry_received"][1]
        enquiry_template.body = template_rows["enquiry_received"][2]

    for payment_template in db.scalars(select(EmailTemplate).where(
            EmailTemplate.template_key == "payment_received")).all():
        if (payment_template.display_name == "Payment received"
                and ("{payment_amount}" not in payment_template.body
                     or "{outstanding_balance}" not in payment_template.body
                     or "{portal_url}" not in payment_template.body)):
            payment_template.subject = template_rows["payment_received"][1]
            payment_template.body = template_rows["payment_received"][2]

    # Bring quotes accepted on earlier builds onto the new fixed payment schedule.
    for accepted_quote in db.scalars(select(Quote).where(Quote.status == "accepted")).all():
        booking = db.get(Booking, accepted_quote.booking_id)
        invoice = db.get(Invoice, accepted_quote.invoice_id) if accepted_quote.invoice_id else None
        if not booking or not invoice or booking.brand != Brand.WBM or not booking.event_date:
            continue
        accepted_on = (accepted_quote.accepted_at.date()
                       if accepted_quote.accepted_at else invoice.issue_date)
        deposit_due = accepted_on + timedelta(days=1)
        balance_due = max(booking.event_date - timedelta(days=45), deposit_due)
        invoice.deposit_due_date = invoice.deposit_due_date or deposit_due
        invoice.due_date = balance_due
        invoice.supply_date = booking.event_date
        booking.balance_due_date = balance_due
        if invoice.notes and invoice.notes.endswith("is due by bank transfer."):
            invoice.notes = (f"Booking fee of £{float(accepted_quote.deposit_amount):,.2f} is due by "
                             f"{deposit_due.strftime('%d %B %Y')}. The remaining balance is due by "
                             f"{balance_due.strftime('%d %B %Y')}.")

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
            create_default_tasks(db, booking.id, kind, booking.event_date)
        db.commit()
