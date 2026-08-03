from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import BusinessProfile, Invoice


TEAL = colors.HexColor("#0f6b63")
INK = colors.HexColor("#17343b")
MUTED = colors.HexColor("#65767c")
PALE = colors.HexColor("#e8f4f2")


def pounds(value) -> str:
    return f"£{float(value or 0):,.2f}"


def invoice_pdf(invoice: Invoice, profile: BusinessProfile, receipt: bool = False) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=17 * mm, bottomMargin=17 * mm, title=invoice.number)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("NormalClean", parent=styles["Normal"], fontName="Helvetica",
                            fontSize=9, leading=13, textColor=INK)
    small = ParagraphStyle("Small", parent=normal, fontSize=8, leading=11, textColor=MUTED)
    right = ParagraphStyle("Right", parent=normal, alignment=TA_RIGHT)
    heading = ParagraphStyle("Heading", parent=styles["Title"], fontName="Helvetica-Bold",
                             fontSize=27, leading=31, textColor=INK, alignment=TA_RIGHT)
    story = []
    contact = "<br/>".join(escape(str(x)) for x in [profile.legal_name, profile.address, profile.phone, profile.email, profile.website] if x)
    header = Table([
        [Paragraph(f"<b>{profile.display_name}</b><br/><font color='#65767c'>{contact}</font>", normal),
         Paragraph("RECEIPT" if receipt else "INVOICE", heading)]
    ], colWidths=[105 * mm, 51 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [header, Spacer(1, 8 * mm), HRFlowable(color=TEAL, thickness=2), Spacer(1, 7 * mm)]

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
    lines = Table([
        [Paragraph("<b>DESCRIPTION</b>", small), Paragraph("<b>AMOUNT</b>", ParagraphStyle("AmountHead", parent=small, alignment=TA_RIGHT))],
        [Paragraph(escape(description), normal), Paragraph(f"<b>{pounds(invoice.total)}</b>", right)]
    ], colWidths=[125 * mm, 31 * mm])
    lines.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), PALE), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#cfdbde")),
                               ("INNERGRID", (0, 0), (-1, -1), .5, colors.HexColor("#cfdbde")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 9),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story += [lines, Spacer(1, 6 * mm)]
    totals = Table([
        ["Subtotal", pounds(invoice.total)], ["VAT", "£0.00"], ["Paid", pounds(invoice.paid)],
        [Paragraph("<b>BALANCE DUE</b>", normal), Paragraph(f"<b>{pounds(invoice.total - invoice.paid)}</b>", right)]
    ], colWidths=[37 * mm, 31 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("TEXTCOLOR", (0, 0), (-1, 2), MUTED),
                                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 1, TEAL),
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
