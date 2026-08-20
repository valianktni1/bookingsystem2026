from decimal import Decimal
from datetime import timezone
from io import BytesIO
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (HRFlowable, Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .models import Booking, Brand, BusinessProfile, ContractAcceptance, FormSubmission, Invoice
from .services import payment_reference


BRANDING_DIR = Path(__file__).parent / "static" / "branding"
BRAND_ASSETS = {
    Brand.WBM: {
        "logo": BRANDING_DIR / "weddings-by-mark-logo.png",
        "awards": BRANDING_DIR / "weddings-by-mark-awards.png",
        "accent": colors.HexColor("#b6924f"),
        "ink": colors.HexColor("#24211c"),
        "pale": colors.HexColor("#f7f3eb"),
    },
    Brand.IVORY: {
        "logo": BRANDING_DIR / "ivory-digital-logo.png",
        "accent": colors.HexColor("#b8862f"),
        "ink": colors.HexColor("#2b271f"),
        "pale": colors.HexColor("#faf4e7"),
    },
}


TEAL = colors.HexColor("#0f6b63")
INK = colors.HexColor("#17343b")
MUTED = colors.HexColor("#65767c")
PALE = colors.HexColor("#e8f4f2")


def pounds(value) -> str:
    return f"£{float(value or 0):,.2f}"


def fitted_image(path, max_width, max_height) -> Image | None:
    if not path or not path.exists():
        return None
    width, height = ImageReader(str(path)).getSize()
    scale = min(max_width / width, max_height / height)
    return Image(str(path), width=width * scale, height=height * scale)


def contract_acceptance_pdf(acceptance: ContractAcceptance, profile: BusinessProfile) -> bytes:
    """Create the protected agreement snapshot with both parties recorded."""
    branding = BRAND_ASSETS.get(profile.brand, BRAND_ASSETS[Brand.WBM])
    accent = branding["accent"]
    ink = branding["ink"]
    pale = branding["pale"]
    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=17 * mm, bottomMargin=17 * mm,
        title=f"{acceptance.contract_title} - signed agreement",
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("AgreementNormal", parent=styles["Normal"], fontName="Helvetica",
                            fontSize=9, leading=13, textColor=ink)
    small = ParagraphStyle("AgreementSmall", parent=normal, fontSize=7.5, leading=10,
                           textColor=MUTED)
    heading = ParagraphStyle("AgreementHeading", parent=styles["Title"], fontName="Helvetica-Bold",
                             fontSize=22, leading=27, textColor=ink)
    section_heading = ParagraphStyle("AgreementSection", parent=normal, fontName="Helvetica-Bold",
                                     fontSize=11, leading=15, textColor=ink, spaceAfter=5)
    story = []
    logo = fitted_image(branding.get("logo"), 70 * mm, 33 * mm)
    identity = [logo] if logo else [Paragraph(f"<b>{escape(profile.display_name)}</b>", normal)]
    header = Table([[identity, Paragraph("SIGNED AGREEMENT", heading)]], colWidths=[90 * mm, 66 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([
        header, Spacer(1, 5 * mm), HRFlowable(color=accent, thickness=2), Spacer(1, 7 * mm),
        Paragraph(escape(acceptance.contract_title), section_heading),
        Paragraph(f"Version {escape(acceptance.contract_version)}", small),
        Spacer(1, 6 * mm),
    ])
    body_blocks = [block.strip() for block in re.split(r"\n\s*\n", acceptance.contract_body or "")
                   if block.strip()]
    for block in body_blocks:
        is_numbered_heading = bool(re.fullmatch(r"\d+\.\s+.+", block))
        is_special_heading = block in {
            "WEDDINGS BY MARK - TERMS AND CONDITIONS",
            "m) DRONE COVERAGE",
        }
        if is_numbered_heading or is_special_heading:
            story.extend([Spacer(1, 2.5 * mm), Paragraph(escape(block), section_heading)])
        elif block.startswith("BY PAYING THE DEPOSIT"):
            story.extend([Spacer(1, 2.5 * mm), Paragraph(f"<b>{escape(block)}</b>", normal)])
        else:
            story.append(Paragraph(escape(block).replace("\n", "<br/>"), normal))
            story.append(Spacer(1, 2.2 * mm))
    story.append(Spacer(1, 6 * mm))

    def signed_at(value) -> str:
        return value.strftime("%d %B %Y at %H:%M UTC") if value else "Not recorded"

    supplier_name = acceptance.supplier_signed_name or "Awaiting supplier countersignature"
    signature_rows = [
        [Paragraph("<b>CLIENT ACCEPTANCE</b>", small), Paragraph("<b>SUPPLIER COUNTERSIGNATURE</b>", small)],
        [Paragraph(f"<b>{escape(acceptance.accepted_name)}</b>", normal),
         Paragraph(f"<b>{escape(supplier_name)}</b>", normal)],
        [Paragraph(escape(acceptance.accepted_email), small),
         Paragraph(escape(profile.email or profile.display_name), small)],
        [Paragraph(signed_at(acceptance.accepted_at), small),
         Paragraph(signed_at(acceptance.supplier_signed_at), small)],
        [Paragraph("Electronically accepted through the secure client portal", small),
         Paragraph("Automatically countersigned on behalf of the supplier after client acceptance"
                   if acceptance.supplier_signed_at else "Supplier countersignature pending", small)],
    ]
    signatures = Table(signature_rows, colWidths=[77 * mm, 77 * mm])
    signatures.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), pale),
        ("BOX", (0, 0), (-1, -1), .7, colors.HexColor("#d8d0c1")),
        ("INNERGRID", (0, 0), (-1, -1), .35, colors.HexColor("#e6dfd3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([
        KeepTogether([Paragraph("Agreement record", section_heading), signatures]),
        Spacer(1, 6 * mm),
        Paragraph(
            "This PDF is generated from the protected agreement snapshot retained by the booking system. "
            "The original wording and acceptance audit are not changed when the live template is edited later.",
            small,
        ),
    ])
    def agreement_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#ded7ca"))
        canvas.setLineWidth(.4)
        canvas.line(18 * mm, 11 * mm, A4[0] - 18 * mm, 11 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 7 * mm, profile.display_name)
        canvas.drawRightString(A4[0] - 18 * mm, 7 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=agreement_footer, onLaterPages=agreement_footer)
    return output.getvalue()


def final_timings_pdf(booking: Booking, submission: FormSubmission,
                      profile: BusinessProfile) -> bytes:
    """Create the photographer's complete, printable final-timings record."""
    branding = BRAND_ASSETS.get(profile.brand, BRAND_ASSETS[Brand.WBM])
    accent, ink, pale = branding["accent"], branding["ink"], branding["pale"]
    values = dict(submission.data or {})
    calculation = dict(values.pop("_calculation", {}) or {})
    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm,
        topMargin=15 * mm, bottomMargin=16 * mm,
        title=f"Final Wedding Timings - {booking.title}",
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("TimingsNormal", parent=styles["Normal"], fontName="Helvetica",
                            fontSize=8.5, leading=12, textColor=ink)
    small = ParagraphStyle("TimingsSmall", parent=normal, fontSize=7.4, leading=10,
                           textColor=MUTED)
    heading = ParagraphStyle("TimingsHeading", parent=styles["Title"], fontName="Helvetica-Bold",
                             fontSize=23, leading=27, textColor=ink, alignment=TA_RIGHT)
    section = ParagraphStyle("TimingsSection", parent=normal, fontName="Helvetica-Bold",
                             fontSize=11.5, leading=15, textColor=ink, spaceBefore=7, spaceAfter=6)
    value_style = ParagraphStyle("TimingsValue", parent=normal, fontSize=8, leading=11)

    def clean(value, fallback="Not supplied") -> str:
        if value is True:
            return "Yes"
        if value is False:
            return "No"
        if value is None or str(value).strip() == "":
            return fallback
        if isinstance(value, list):
            return ", ".join(str(item) for item in value) or fallback
        return str(value)

    def duration(minutes) -> str:
        if minutes is None:
            return "Check package"
        amount = max(0, int(minutes or 0))
        hours, remainder = divmod(amount, 60)
        parts = []
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if remainder:
            parts.append(f"{remainder} minutes")
        return " ".join(parts) or "0 minutes"

    def submitted_time(value) -> str:
        if not value:
            return "Not recorded"
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        local = aware.astimezone(ZoneInfo("Europe/London"))
        return local.strftime("%d %B %Y at %H:%M %Z")

    logo = fitted_image(branding.get("logo"), 68 * mm, 30 * mm)
    identity = [logo] if logo else [Paragraph(f"<b>{escape(profile.display_name)}</b>", normal)]
    header = Table([[identity, Paragraph("FINAL WEDDING<br/>TIMINGS", heading)]],
                   colWidths=[98 * mm, 63 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story = [header, Spacer(1, 4 * mm), HRFlowable(color=accent, thickness=2), Spacer(1, 5 * mm)]

    wedding_rows = [
        [Paragraph("<b>COUPLE</b>", small), Paragraph(escape(booking.title), normal),
         Paragraph("<b>WEDDING DATE</b>", small),
         Paragraph(booking.event_date.strftime("%d %B %Y") if booking.event_date else "Not set", normal)],
        [Paragraph("<b>PACKAGE</b>", small), Paragraph(escape(clean(booking.package_name)), normal),
         Paragraph("<b>SUBMITTED</b>", small), Paragraph(submitted_time(submission.submitted_at), normal)],
    ]
    wedding = Table(wedding_rows, colWidths=[27 * mm, 55 * mm, 30 * mm, 49 * mm])
    wedding.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d7dfdd")),
        ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#d7dfdd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([wedding, Paragraph("Coverage summary", section)])

    status_labels = {
        "within": "Fits included coverage",
        "within_grace": "Within 15-minute grace",
        "over": f"Over by {duration(calculation.get('over_standard_minutes'))}",
        "package_review": "Package needs checking",
    }
    coverage_rows = [
        ["Suggested start", clean(calculation.get("suggested_start")),
         "Expected finish", clean(calculation.get("expected_finish"))],
        ["Expected coverage", duration(calculation.get("coverage_minutes")),
         "Package allowance", duration(calculation.get("package_allowance_minutes"))],
        ["Coverage result", status_labels.get(calculation.get("status"), "Check timings"),
         "Preparation departure", clean(calculation.get("prep_departure"))],
    ]
    coverage = Table([[Paragraph(f"<b>{escape(str(label))}</b>", small),
                       Paragraph(escape(clean(value)), value_style),
                       Paragraph(f"<b>{escape(str(label2))}</b>", small),
                       Paragraph(escape(clean(value2)), value_style)]
                      for label, value, label2, value2 in coverage_rows],
                     colWidths=[32 * mm, 48 * mm, 36 * mm, 45 * mm])
    coverage.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d7dfdd")),
        ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#e3e8e7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(coverage)
    if calculation.get("coverage_warning"):
        story.extend([Spacer(1, 3 * mm), Paragraph(
            f"<b>Coverage warning:</b> These timings exceed the included coverage by "
            f"{escape(duration(calculation.get('over_standard_minutes')))}. Nothing has been charged or changed automatically.",
            normal,
        )])
    if calculation.get("travel_warning"):
        story.extend([Spacer(1, 2 * mm), Paragraph(
            f"<b>Private preparation/travel warning:</b> Only "
            f"{escape(duration(calculation.get('prep_window_minutes')))} remains for preparation photographs before departure.",
            normal,
        )])

    story.append(Paragraph("Wedding-day run sheet", section))
    timeline_rows = [[Paragraph("<b>TIME</b>", small), Paragraph("<b>EVENT</b>", small),
                      Paragraph("<b>DETAIL</b>", small)]]
    for item in calculation.get("timeline") or []:
        timeline_rows.append([
            Paragraph(escape(clean(item.get("time"))), value_style),
            Paragraph(f"<b>{escape(clean(item.get('event')))}</b>", value_style),
            Paragraph(escape(clean(item.get("detail"), "")), value_style),
        ])
    timeline = Table(timeline_rows, colWidths=[24 * mm, 60 * mm, 77 * mm], repeatRows=1)
    timeline.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), pale),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d7dfdd")),
        ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#e3e8e7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(timeline)

    labels = {
        "ceremony_time": "Ceremony time", "ceremony_duration": "Ceremony duration (minutes)",
        "ceremony_venue": "Ceremony venue and address", "reception_same": "Reception at the same venue",
        "reception_venue": "Reception venue and address", "prep_photos": "Preparation photographs",
        "prep_person": "Who is getting ready", "prep_venue": "Preparation venue and address",
        "travel_minutes": "Travel to ceremony (minutes)", "start_choice": "Preferred photography start",
        "requested_start": "Requested earlier start", "prep_notes": "Preparation notes",
        "second_prep": "Second preparation location", "group_photo_time": "Group photograph time",
        "meal_time": "Wedding breakfast / meal time", "speeches_time": "Speeches time",
        "speeches_position": "Speeches position", "evening_time": "Evening guests arrive",
        "cake_time": "Cake cutting", "first_dance_time": "First dance",
        "later_event": "Essential event after first dance", "later_event_name": "Later event",
        "later_event_time": "Later event time", "extra_stops": "Additional stops or venues",
        "day_contact": "Wedding-day contact", "day_mobile": "Wedding-day mobile",
        "coordinator": "Venue coordinator", "group_count": "Formal group photographs",
        "important_notes": "Important details and requests",
    }
    story.extend([PageBreak(), Paragraph("Complete submitted answers", section)])
    answer_rows = []
    for key, label in labels.items():
        answer_rows.append([
            Paragraph(f"<b>{escape(label)}</b>", small),
            Paragraph(escape(clean(values.get(key))).replace("\n", "<br/>"), value_style),
        ])
    answers = Table(answer_rows, colWidths=[55 * mm, 106 * mm])
    answers.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d7dfdd")),
        ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#e3e8e7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), pale),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(answers)

    def timings_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d7dfdd"))
        canvas.setLineWidth(.4)
        canvas.line(16 * mm, 10 * mm, A4[0] - 16 * mm, 10 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 6 * mm, f"{profile.display_name} · Private planning copy")
        canvas.drawRightString(A4[0] - 16 * mm, 6 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=timings_footer, onLaterPages=timings_footer)
    return output.getvalue()


def invoice_pdf(invoice: Invoice, profile: BusinessProfile, receipt: bool = False) -> bytes:
    branding = BRAND_ASSETS.get(invoice.brand, BRAND_ASSETS[Brand.WBM])
    accent = branding["accent"]
    ink = branding["ink"]
    pale = branding["pale"]
    output = BytesIO()
    bottom_margin = 37 * mm if invoice.brand == Brand.WBM else 17 * mm
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=17 * mm, bottomMargin=bottom_margin, title=invoice.number)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("NormalClean", parent=styles["Normal"], fontName="Helvetica",
                            fontSize=9, leading=13, textColor=ink)
    small = ParagraphStyle("Small", parent=normal, fontSize=8, leading=11, textColor=MUTED)
    right = ParagraphStyle("Right", parent=normal, alignment=TA_RIGHT)
    heading = ParagraphStyle("Heading", parent=styles["Title"], fontName="Helvetica-Bold",
                             fontSize=27, leading=31, textColor=ink, alignment=TA_RIGHT)
    story = []
    contact = "<br/>".join(escape(str(x)) for x in [profile.legal_name, profile.address, profile.phone, profile.email, profile.website] if x)
    if invoice.brand == Brand.WBM:
        logo = fitted_image(branding.get("logo"), 65 * mm, 40 * mm)
        identity = [logo, Spacer(1, 2.5 * mm)] if logo else []
    else:
        logo = fitted_image(branding.get("logo"), 70 * mm, 25 * mm)
        identity = [logo, Spacer(1, 2.5 * mm)] if logo else []
    if not identity:
        identity = [Paragraph(f"<b>{profile.display_name}</b>", normal)]
    identity.append(Paragraph(f"<font color='#65767c'>{contact}</font>", small))
    document_title = ("RECEIPT" if receipt else
                      "VOID INVOICE" if invoice.status == "void" else
                      "CANCELLED INVOICE" if invoice.status == "cancelled" else
                      "INVOICE")
    header = Table([[identity, Paragraph(document_title, heading)]], colWidths=[105 * mm, 51 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [header, Spacer(1, 6 * mm), HRFlowable(color=accent, thickness=2), Spacer(1, 7 * mm)]

    client = invoice.booking.client
    client_name = client.company_name or invoice.booking.title
    client_lines = "<br/>".join(escape(str(x)) for x in [client_name, client.email, client.phone, client.address] if x)
    meta_lines = [f"<b>Number</b>&nbsp;&nbsp; {invoice.number}", f"<b>Issue date</b>&nbsp;&nbsp; {invoice.issue_date.strftime('%d %B %Y')}"]
    if invoice.deposit_due_date:
        meta_lines.append(f"<b>Booking fee due</b>&nbsp;&nbsp; {invoice.deposit_due_date.strftime('%d %B %Y')}")
    if invoice.due_date:
        meta_lines.append(f"<b>Final balance due</b>&nbsp;&nbsp; {invoice.due_date.strftime('%d %B %Y')}")
    if invoice.supply_date:
        meta_lines.append(f"<b>Supply date</b>&nbsp;&nbsp; {invoice.supply_date.strftime('%d %B %Y')}")
    details = Table([
        [Paragraph("<font color='#65767c'><b>BILL TO</b></font>", small), Paragraph("<br/>".join(meta_lines), right)],
        [Paragraph(client_lines, normal), ""]
    ], colWidths=[94 * mm, 62 * mm])
    details.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [details, Spacer(1, 9 * mm)]

    description = invoice.description or invoice.booking.package_name or invoice.booking.venue_or_project or "Professional services"
    rows = [[Paragraph("<b>DESCRIPTION</b>", small),
             Paragraph("<b>AMOUNT</b>", ParagraphStyle("AmountHead", parent=small, alignment=TA_RIGHT))]]
    item_detail = ParagraphStyle("ItemDetail", parent=normal, fontSize=7.6, leading=10.6,
                                 textColor=colors.HexColor("#526268"), spaceBefore=2)
    item_starts = []
    detail_rows = []
    if invoice.line_items:
        for item in invoice.line_items:
            item_starts.append(len(rows))
            name = escape(str(item.get("name") or item.get("description") or "Service"))
            description = str(item.get("description") or "").replace("•", "-").strip()
            rows.append([Paragraph(f"<b>{name}</b>", normal),
                         Paragraph(f"<b>{pounds(item.get('total'))}</b>", right)])
            if description and escape(description) != name:
                for line in (line.strip() for line in description.splitlines()):
                    if line:
                        detail_rows.append(len(rows))
                        rows.append([Paragraph(escape(line), item_detail), ""])
    else:
        item_starts.append(len(rows))
        rows.append([Paragraph(escape(description), normal), Paragraph(f"<b>{pounds(invoice.total)}</b>", right)])
    lines = Table(rows, colWidths=[125 * mm, 31 * mm], repeatRows=1)
    line_style = [
        ("BACKGROUND", (0, 0), (-1, 0), pale),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d9d2c6")),
        ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#cfdbde")),
        ("LINEBEFORE", (1, 0), (1, -1), .5, colors.HexColor("#cfdbde")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
    ]
    for row_index in item_starts:
        if row_index > 1:
            line_style.append(("LINEABOVE", (0, row_index), (-1, row_index), .5, colors.HexColor("#cfdbde")))
        line_style += [("TOPPADDING", (0, row_index), (-1, row_index), 8),
                       ("BOTTOMPADDING", (0, row_index), (-1, row_index), 3)]
    for row_index in detail_rows:
        line_style += [("TOPPADDING", (0, row_index), (-1, row_index), 1),
                       ("BOTTOMPADDING", (0, row_index), (-1, row_index), 1)]
    lines.setStyle(TableStyle(line_style))
    story += [lines, Spacer(1, 6 * mm)]
    closed = invoice.status in ("void", "cancelled")
    outstanding = Decimal("0") if closed else invoice.total - invoice.paid
    refunded = sum(
        -Decimal(payment.amount)
        for payment in invoice.payments
        if payment.payment_type == "refund" and Decimal(payment.amount) < 0
    )
    gross_received = Decimal(invoice.paid or 0) + refunded
    total_rows = [["Subtotal", pounds(invoice.total)], ["VAT", "£0.00"]]
    if refunded > 0:
        total_rows.extend([
            ["Payments received", pounds(gross_received)],
            ["Refunded", f"-{pounds(refunded)}"],
            ["Payment retained", pounds(invoice.paid)],
        ])
    else:
        total_rows.append(["Paid", pounds(invoice.paid)])
    total_rows.append([
        Paragraph("<b>TOTAL OUTSTANDING</b>", normal),
        Paragraph(f"<b>{pounds(outstanding)}</b>", right),
    ])
    totals = Table(total_rows, colWidths=[48 * mm, 31 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("TEXTCOLOR", (0, 0), (-1, 2), MUTED),
                                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 1, accent),
                                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [totals, Spacer(1, 6 * mm)]

    expected_deposit = min(invoice.total, invoice.booking.deposit_amount or Decimal("0"))
    schedule_rows = []
    if not closed and invoice.payment_schedule:
        for item in invoice.payment_schedule:
            due = item.get("due_date") or "To be confirmed"
            if hasattr(due, "strftime"):
                due = due.strftime("%d %B %Y")
            elif due and due != "To be confirmed":
                try:
                    from datetime import date
                    due = date.fromisoformat(str(due)).strftime("%d %B %Y")
                except ValueError:
                    due = str(due)
            schedule_rows.append([
                Paragraph(escape(str(item.get("label") or "Scheduled payment")), normal),
                Paragraph(f"<b>{pounds(item.get('amount'))}</b>", right),
                Paragraph(escape(str(item.get("status") or "Due")).replace("_", " ").title(), small),
                Paragraph(escape(str(due)), right),
            ])
    elif (not closed and invoice.brand == Brand.WBM
          and invoice.deposit_due_date and expected_deposit > 0):
        schedule_rows = [
            [Paragraph("Booking fee", normal), Paragraph(f"<b>{pounds(expected_deposit)}</b>", right),
             Paragraph("Due", small), Paragraph(invoice.deposit_due_date.strftime("%d %B %Y"), right)],
            [Paragraph("Remaining balance", normal), Paragraph(f"<b>{pounds(invoice.total - expected_deposit)}</b>", right),
             Paragraph("Due", small), Paragraph(invoice.due_date.strftime("%d %B %Y") if invoice.due_date else "To be confirmed", right)],
        ]
    if schedule_rows:
        payment_schedule = Table([
            [Paragraph("<b>PAYMENT SCHEDULE</b>", small), "", "", ""],
            *schedule_rows,
        ], colWidths=[40 * mm, 28 * mm, 24 * mm, 64 * mm])
        payment_schedule.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), pale),
            ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d9d2c6")),
            ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#d9d2c6")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story += [KeepTogether([payment_schedule]), Spacer(1, 6 * mm)]
    else:
        story.append(Spacer(1, 2 * mm))

    bank = profile.bank_details or {}
    bank_lines = []
    for label, key in [("Account name", "account_name"), ("Sort code", "sort_code"), ("Account number", "account_number")]:
        if bank.get(key):
            bank_lines.append(f"<b>{label}:</b> {escape(str(bank[key]))}")
    if invoice.status == "void" and not receipt:
        note_parts = ["<b>VOID INVOICE — no payment is due.</b>",
                      "This invoice number has been retained in the financial record and has not been reused.",
                      "No VAT has been charged on this invoice."]
    elif invoice.status == "cancelled" and not receipt:
        note_parts = ["<b>CANCELLED BOOKING — no further payment is due.</b>",
                      "The unpaid balance has been closed. The invoice number and all payment/refund history have been retained.",
                      "No VAT has been charged on this invoice."]
    else:
        note_parts = ["No VAT has been charged on this invoice."]
        if not receipt:
            reference = payment_reference(invoice.booking, invoice.number)
            note_parts.insert(
                0,
                f"<b>PAYMENT REFERENCE: {escape(reference)}</b><br/>"
                f"Please use <b>{escape(reference)}</b> for every bank transfer for this wedding.",
            )
        if bank_lines and not receipt:
            note_parts.append("<br/>".join(bank_lines))
    if invoice.notes:
        note_parts.append(escape(invoice.notes))
    box = Table([[Paragraph("<br/><br/>".join(note_parts), normal)]], colWidths=[156 * mm])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f9fa")),
                             ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#dce5e7")),
                             ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                             ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    story.append(box)
    def branded_footer(canvas, _doc):
        awards_path = branding.get("awards")
        if invoice.brand != Brand.WBM or not awards_path or not awards_path.exists():
            return
        path = awards_path
        width, height = ImageReader(str(path)).getSize()
        scale = min((38 * mm) / width, (30 * mm) / height)
        draw_width, draw_height = width * scale, height * scale
        x = (A4[0] - draw_width) / 2
        y = 4 * mm
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#e2d8c5"))
        canvas.setLineWidth(.6)
        canvas.line(18 * mm, y + draw_height + 2.5 * mm, A4[0] - 18 * mm, y + draw_height + 2.5 * mm)
        canvas.drawImage(str(path), x, y, width=draw_width, height=draw_height,
                         preserveAspectRatio=True, mask="auto")
        canvas.restoreState()

    doc.build(story, onFirstPage=branded_footer, onLaterPages=branded_footer)
    return output.getvalue()
