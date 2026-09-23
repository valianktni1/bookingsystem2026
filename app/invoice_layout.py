"""Native WBM invoice presentation; saved figures and descriptions remain authoritative."""
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from .models import Invoice, BusinessProfile, Brand
from .pdf import BRAND_ASSETS, MUTED, fitted_image, invoice_description_lines, pounds
from .quote_templates import invoice_bank_details
from .services import payment_reference
from .payment_display import allocated_schedule

FONT_DIR = Path(__file__).parent / "static" / "fonts"
pdfmetrics.registerFont(TTFont("WBMInvoice", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("WBMInvoice-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFontFamily("WBMInvoice", normal="WBMInvoice", bold="WBMInvoice-Bold",
                              italic="WBMInvoice", boldItalic="WBMInvoice-Bold")

def native_invoice_pdf(invoice: Invoice, profile: BusinessProfile, receipt: bool = False) -> bytes:
    branding = BRAND_ASSETS.get(invoice.brand, BRAND_ASSETS[Brand.WBM])
    accent = branding["accent"]
    ink = branding["ink"]
    pale = branding["pale"]
    output = BytesIO()
    bottom_margin = 25 * mm
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=12 * mm, bottomMargin=bottom_margin, title=invoice.number)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("NormalClean", parent=styles["Normal"], fontName="WBMInvoice",
                            fontSize=9, leading=12, textColor=ink)
    small = ParagraphStyle("Small", parent=normal, fontSize=8, leading=10.5, textColor=MUTED)
    right = ParagraphStyle("Right", parent=normal, alignment=TA_RIGHT)
    heading = ParagraphStyle("Heading", parent=styles["Title"], fontName="WBMInvoice-Bold",
                             fontSize=23, leading=27, textColor=ink, alignment=TA_RIGHT)
    story = []
    contact = "<br/>".join(escape(str(x)) for x in [profile.legal_name, profile.address, profile.phone, profile.email, profile.website] if x)
    logo = fitted_image(branding.get("logo"), 52 * mm, 24 * mm)
    identity = [logo] if logo else [Paragraph(escape(profile.display_name), normal)]
    document_title = ("RECEIPT" if receipt else
                      "VOID INVOICE" if invoice.status == "void" else
                      "CANCELLED INVOICE" if invoice.status == "cancelled" else
                      "INVOICE")
    header = Table([[identity, [Paragraph(document_title, heading), Spacer(1, 2 * mm),
                               Paragraph(contact, ParagraphStyle("ContactRight", parent=small, alignment=TA_RIGHT))]]],
                   colWidths=[72 * mm, 96 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [header, Spacer(1, 3 * mm), HRFlowable(width="100%", color=accent, thickness=1), Spacer(1, 4 * mm)]

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
        [Paragraph("<font color='#65767c'><b>BILL TO</b></font><br/>" + client_lines, normal),
         Paragraph("<br/>".join(meta_lines), right)]
    ], colWidths=[90 * mm, 78 * mm])
    details.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [details, Spacer(1, 4 * mm)]

    description = invoice.description or invoice.booking.package_name or invoice.booking.venue_or_project or "Professional services"
    rows = [[Paragraph("<b>DESCRIPTION</b>", small),
             Paragraph("<b>AMOUNT</b>", ParagraphStyle("AmountHead", parent=small, alignment=TA_RIGHT))]]
    item_detail = ParagraphStyle("ItemDetail", parent=normal, fontSize=9, leading=12,
                                 textColor=ink, leftIndent=8)
    item_starts = []
    detail_rows = []
    first_details = []
    items = invoice.line_items or [{"name": "", "description": description, "total": invoice.total}]
    for item in items:
        saved_name = str(item.get("name") or "").strip()
        saved_description = str(item.get("description") or "")
        parts = invoice_description_lines(saved_description)
        if not saved_name:
            saved_name = parts.pop(0) if parts else "Professional services"
        elif len(parts) == 1 and parts[0] == saved_name:
            parts = []
        item_starts.append(len(rows))
        rows.append([Paragraph(f"<b>{escape(saved_name)}</b>", normal),
                     Paragraph(f"<b>{pounds(item.get('total'))}</b>", right)])
        if parts:
            first_details.append(len(rows) - 1)
        for line in parts:
            detail_rows.append(len(rows))
            rows.append([Paragraph(escape(line), item_detail), ""])
    lines = Table(rows, colWidths=[137 * mm, 31 * mm], repeatRows=1, splitInRow=1)
    line_style = [
        ("BACKGROUND", (0, 0), (-1, 0), pale),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d9d2c6")),
        ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#cfdbde")),
        ("LINEBEFORE", (1, 0), (1, -1), .5, colors.HexColor("#cfdbde")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ]
    for row_index in item_starts:
        if row_index > 1:
            line_style.append(("LINEABOVE", (0, row_index), (-1, row_index), .5, colors.HexColor("#cfdbde")))
        line_style += [("TOPPADDING", (0, row_index), (-1, row_index), 8),
                       ("BOTTOMPADDING", (0, row_index), (-1, row_index), 3)]
    for row_index in detail_rows:
        line_style += [("TOPPADDING", (0, row_index), (-1, row_index), .5),
                       ("BOTTOMPADDING", (0, row_index), (-1, row_index), .5)]
    for row_index in first_details:
        line_style.append(("NOSPLIT", (0, row_index), (-1, row_index + 1)))
    lines.setStyle(TableStyle(line_style))
    story += [lines, Spacer(1, 3 * mm)]
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
    totals.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "WBMInvoice"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("TEXTCOLOR", (0, 0), (-1, 2), MUTED),
                                ("FONTNAME", (0, -1), (-1, -1), "WBMInvoice-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 1, accent),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story += [KeepTogether([totals]), Spacer(1, 3 * mm)]

    expected_deposit = min(invoice.total, invoice.booking.deposit_amount or Decimal("0"))
    schedule_rows = []
    if not closed and invoice.payment_schedule:
        for item in allocated_schedule(invoice):
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
                Paragraph(escape(str(item.get("status") or "Scheduled")).replace("_", " ").title(), small),
                Paragraph(escape(str(due)), right),
            ])
    elif (not closed and invoice.brand == Brand.WBM
          and invoice.deposit_due_date and expected_deposit > 0):
        schedule_rows = [
            [Paragraph("Booking fee", normal), Paragraph(f"<b>{pounds(expected_deposit)}</b>", right),
             Paragraph("Paid" if invoice.paid >= expected_deposit else "Part paid" if invoice.paid > 0 else "Scheduled", small), Paragraph(invoice.deposit_due_date.strftime("%d %B %Y"), right)],
            [Paragraph("Remaining balance", normal), Paragraph(f"<b>{pounds(invoice.total - expected_deposit)}</b>", right),
             Paragraph("Paid" if invoice.paid >= invoice.total else "Part paid" if invoice.paid > expected_deposit else "Scheduled", small), Paragraph(invoice.due_date.strftime("%d %B %Y") if invoice.due_date else "To be confirmed", right)],
        ]
    if schedule_rows:
        payment_schedule = Table([
            [Paragraph("<b>PAYMENT SCHEDULE</b>", small), "", "", ""],
            *schedule_rows,
        ], colWidths=[62 * mm, 28 * mm, 28 * mm, 50 * mm])
        payment_schedule.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), pale),
            ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d9d2c6")),
            ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#d9d2c6")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story += [KeepTogether([payment_schedule]), Spacer(1, 3 * mm)]
    else:
        story.append(Spacer(1, 2 * mm))

    bank = invoice_bank_details(invoice, profile)
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
        note_parts.append("<br/>".join(escape(line) for line in invoice_description_lines(invoice.notes)))
    box = Table([[Paragraph("<br/>".join(note_parts), normal)]], colWidths=[168 * mm])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f9fa")),
                             ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#dce5e7")),
                             ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                             ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    story.append(box)
    def branded_footer(canvas, _doc):
        if _doc.page > 1:
            canvas.saveState()
            canvas.setFont("WBMInvoice-Bold", 9)
            canvas.setFillColor(ink)
            canvas.drawString(18 * mm, A4[1] - 8 * mm, f"{document_title} {invoice.number} - continued")
            canvas.restoreState()
        awards_path = branding.get("awards")
        if invoice.brand != Brand.WBM or not awards_path or not awards_path.exists():
            return
        path = awards_path
        width, height = ImageReader(str(path)).getSize()
        scale = min((25 * mm) / width, (16 * mm) / height)
        draw_width, draw_height = width * scale, height * scale
        x = (A4[0] - draw_width) / 2
        y = 3 * mm
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#e2d8c5"))
        canvas.setLineWidth(.6)
        canvas.line(18 * mm, y + draw_height + 2.5 * mm, A4[0] - 18 * mm, y + draw_height + 2.5 * mm)
        canvas.drawImage(str(path), x, y, width=draw_width, height=draw_height,
                         preserveAspectRatio=True, mask="auto")
        canvas.setFont("WBMInvoice", 8)
        canvas.setFillColor(ink)
        canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f"{invoice.number} | Page {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=branded_footer, onLaterPages=branded_footer)
    return output.getvalue()
