from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Admin, Booking, Brand, BusinessProfile, Client, InvoiceCounter, RecordKind, RecordStatus
from .security import hash_password
from .services import create_default_tasks


def bootstrap(db: Session) -> None:
    settings = get_settings()
    if not db.scalar(select(Admin).limit(1)):
        db.add(Admin(email=settings.admin_email.lower(), password_hash=hash_password(settings.admin_password)))

    profiles = {
        Brand.WBM: ("Weddings By Mark", "WBM", "mark@perfectweddingsbymark.uk", "perfectweddingsbymark.uk"),
        Brand.IVORY: ("Ivory Digital", "ID", "sales@ivorydigital.uk", "ivorydigital.uk"),
    }
    for brand, (name, prefix, email, website) in profiles.items():
        profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == brand))
        if not profile:
            db.add(BusinessProfile(brand=brand, display_name=name, invoice_prefix=prefix, email=email,
                                   phone="07712 117357", website=website,
                                   address="220 Ashurst Road, Manchester M22 5AX"))
        else:
            profile.phone = profile.phone or "07712 117357"
            profile.website = profile.website or website
            profile.address = profile.address or "220 Ashurst Road, Manchester M22 5AX"

    if not db.get(InvoiceCounter, "global"):
        db.add(InvoiceCounter(key="global", value=settings.invoice_start))
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
