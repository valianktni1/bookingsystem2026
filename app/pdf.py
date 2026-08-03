from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Brand, BusinessProfile, Invoice


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


def invoice_pdf(invoice: Invoice, profile: BusinessProfile, receipt: bool = False) -> bytes:
    branding = BRAND_ASSETS.get(invoice.brand, BRAND_ASSETS[Brand.WBM])
    accent = branding["accent"]
    ink = branding["ink"]
    pale = branding["pale"]
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=17 * mm, bottomMargin=17 * mm, title=invoice.number)
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
        logo = fitted_image(branding.get("logo"), 43 * mm, 29 * mm)
        awards = fitted_image(branding.get("awards"), 57 * mm, 44 * mm)
        if logo and awards:
            brand_marks = Table([[logo, awards]], colWidths=[46 * mm, 59 * mm])
            brand_marks.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            identity = [brand_marks, Spacer(1, 2.5 * mm)]
        else:
            identity = [item for item in (logo, awards) if item]
    else:
        logo = fitted_image(branding.get("logo"), 70 * mm, 25 * mm)
        identity = [logo, Spacer(1, 2.5 * mm)] if logo else []
    if not identity:
        identity = [Paragraph(f"<b>{profile.display_name}</b>", normal)]
    identity.append(Paragraph(f"<font color='#65767c'>{contact}</font>", small))
    header = Table([
        [identity,
         Paragraph("RECEIPT" if receipt else "INVOICE", heading)]
    ], colWidths=[105 * mm, 51 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [header, Spacer(1, 6 * mm), HRFlowable(color=accent, thickness=2), Spacer(1, 7 * mm)]

    client = invoice.booking.client
    client_name = client.company_name or invoice.booking.title
    client_lines = "<br/>".join(escape(str(x)) for x in [client_name, client.email, client.phone, client.address] if x)
    meta_lines = [f"<b>Number</b>&nbsp;&nbsp; {invoice.number}", f"<b>Issue date</b>&nbsp;&nbsp; {invoice.issue_date.strftime('%d %B %Y')}"]
    if invoice.due_date:
        meta_lines.append(f"<b>Due date</b>&nbsp;&nbsp; {invoice.due_date.strftime('%d %B %Y')}")
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
    if invoice.line_items:
        for item in invoice.line_items:
            name = escape(str(item.get("name") or item.get("description") or "Service"))
            rows.append([Paragraph(name, normal), Paragraph(f"<b>{pounds(item.get('total'))}</b>", right)])
    else:
        rows.append([Paragraph(escape(description), normal), Paragraph(f"<b>{pounds(invoice.total)}</b>", right)])
    lines = Table(rows, colWidths=[125 * mm, 31 * mm])
    lines.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), pale), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d9d2c6")),
                               ("INNERGRID", (0, 0), (-1, -1), .5, colors.HexColor("#cfdbde")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 9),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story += [lines, Spacer(1, 6 * mm)]
    totals = Table([
        ["Subtotal", pounds(invoice.total)], ["VAT", "£0.00"], ["Paid", pounds(invoice.paid)],
        [Paragraph("<b>BALANCE DUE</b>", normal), Paragraph(f"<b>{pounds(invoice.total - invoice.paid)}</b>", right)]
    ], colWidths=[37 * mm, 31 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("TEXTCOLOR", (0, 0), (-1, 2), MUTED),
                                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 1, accent),
                                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [totals, Spacer(1, 8 * mm)]

    bank = profile.bank_details or {}
    bank_lines = []
    for label, key in [("Account name", "account_name"), ("Sort code", "sort_code"), ("Account number", "account_number")]:
        if bank.get(key):
            bank_lines.append(f"<b>{label}:</b> {escape(str(bank[key]))}")
    note_parts = ["No VAT has been charged on this invoice."]
    if not receipt:
        note_parts.insert(0, f"Please use <b>{invoice.number}</b> as your bank-transfer reference.")
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
    doc.build(story)
    return output.getvalue()
