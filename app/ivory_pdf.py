"""Ivory quotation and invoice layout, based on Mark's supplied quotation."""
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONTS = Path(__file__).parent / "static" / "fonts"
for suffix, name in [("", "IvoryDocument"), ("-Bold", "IvoryDocument-Bold")]:
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(FONTS / f"DejaVuSans{suffix}.ttf")))
pdfmetrics.registerFontFamily("IvoryDocument", normal="IvoryDocument", bold="IvoryDocument-Bold", italic="IvoryDocument", boldItalic="IvoryDocument-Bold")


def money(v):
    return f"£{Decimal(str(v or 0)):,.2f}"


def document(profile, *, title, reference, customer, email, address, intro, lines, terms, issued=None,
             due=None, paid=0, payments=None, invoice=False, receipt=False, bank=None):
    output=BytesIO()
    doc=SimpleDocTemplate(output, pagesize=A4, topMargin=17*mm, bottomMargin=17*mm, leftMargin=20*mm, rightMargin=20*mm, title=reference)
    ink=colors.HexColor("#2b2925"); gold=colors.HexColor("#b38a43"); muted=colors.HexColor("#626e73"); pale=colors.HexColor("#f7f4e9"); rule=colors.HexColor("#d6d1c7")
    normal=ParagraphStyle("IvoryBody",fontName="IvoryDocument",fontSize=9,leading=13,textColor=ink)
    small=ParagraphStyle("IvorySmall",parent=normal,fontSize=7.5,leading=10,textColor=muted)
    right=ParagraphStyle("IvoryRight",parent=normal,alignment=TA_RIGHT)
    heading=ParagraphStyle("IvoryHeading",parent=right,fontName="IvoryDocument-Bold",fontSize=21,leading=27)
    def p(text, style=normal):
        return Paragraph(escape(str(text or "")).replace("\n","<br/>"),style)
    def table(data,widths):
        t=Table(data,colWidths=widths,hAlign="LEFT")
        t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]));return t
    logo=Path(__file__).parent/"static"/"branding"/"ivory-digital-logo.png"
    identity=[]
    if logo.exists():
        from reportlab.lib.utils import ImageReader
        w,h=ImageReader(str(logo)).getSize(); identity.append(Image(str(logo),width=65*mm,height=65*mm*h/w,hAlign="LEFT"))
    else:
        identity.append(p(profile.display_name,heading))
    identity.extend([Spacer(1,3*mm),p(" | ".join(x for x in [profile.legal_name,profile.display_name] if x),small),
                     p(" | ".join(x for x in [profile.phone,profile.email] if x),small),p(profile.website,small)])
    story=[table([[identity,p(title,heading)]],[100*mm,70*mm]),Spacer(1,4*mm),HRFlowable(width="100%",thickness=1,color=gold),Spacer(1,4*mm)]
    customer_block=[p("BILL TO" if invoice else "PREPARED FOR",small),p(customer),p(email,small)]
    if address:customer_block.append(p(address,small))
    meta=[p(reference,right)]
    if issued:meta.append(p("Issued: "+issued.strftime("%d %B %Y"),right))
    if due:meta.append(p("Payment due: "+due.strftime("%d %B %Y"),right))
    story.extend([table([[customer_block,meta]],[100*mm,70*mm]),Spacer(1,5*mm)])
    if intro:story.extend([p(intro),Spacer(1,4*mm)])
    rows=[[p("DESCRIPTION",small),p("AMOUNT",ParagraphStyle("IvoryLabelRight",parent=small,alignment=TA_RIGHT))]]
    total=Decimal("0");monthly=[]
    for line in lines:
        if line.get("kind") == "monthly":
            monthly.append(line);continue
        selected=line.get("selected",True)
        if invoice and not selected:continue
        kind=line.get("kind","one_off");amount=Decimal(str(line.get("amount",line.get("total",0))))
        if selected and kind=="one_off":total+=amount
        label="Included" if kind=="included" else money(amount)
        if not selected:label+=" (optional)"
        desc=[p(line["name"],ParagraphStyle("IvoryLineName",parent=normal,fontName="IvoryDocument-Bold"))]
        if line.get("description"):desc.extend([Spacer(1,1.5*mm),p(line["description"],small)])
        rows.append([desc,p(label,right)])
    t=Table(rows,colWidths=[128*mm,42*mm],repeatRows=1,hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),pale),("BOX",(0,0),(-1,-1),.5,rule),("INNERGRID",(0,0),(-1,-1),.4,rule),
                          ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
                          ("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9)]))
    story.extend([t,Spacer(1,4*mm)])
    totals=[[p("INVOICE TOTAL" if invoice else "ONE-OFF TOTAL"),p(money(total),right)]]
    if invoice:
        totals.append([p("Payment received"),p(money(paid),right)])
        totals.append([p("BALANCE REMAINING"),p(money(total-Decimal(str(paid))),right)])
    story.extend([KeepTogether(table(totals,[120*mm,50*mm])),Spacer(1,2*mm),p("No VAT charged.",small)])
    for payment in payments or []:
        story.append(p(f"Payment received {payment.paid_date.strftime('%d %B %Y')}: {money(payment.amount)}",small))
    if monthly and not invoice:
        story.extend([Spacer(1,4*mm),p("MONTHLY SERVICES - SEPARATE FROM THE ONE-OFF TOTAL")])
        for line in monthly:
            story.append(p(f"{line['name']}: {money(line['amount'])}/month - {'selected' if line.get('selected') else 'optional, not selected'}",small))
    if terms:
        notes=Table([[p(terms,small)]],colWidths=[170*mm]);notes.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),pale),("BOX",(0,0),(-1,-1),.5,rule),
                ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9)]))
        story.extend([Spacer(1,4*mm),notes])
    if invoice and not receipt and total>Decimal(str(paid)):
        bank=bank or {}
        text="\n".join(f"{label}: {bank[key]}" for label,key in [("Account name","account_name"),("Sort code","sort_code"),("Account number","account_number")] if bank.get(key))
        story.extend([Spacer(1,4*mm),KeepTogether([p("BANK TRANSFER"),p(text,small),p("Payment reference: "+reference,small)])])
    def footer(canvas, doc):
        canvas.setFont("IvoryDocument",7);canvas.setFillColor(muted)
        canvas.drawString(20*mm,10*mm,reference);canvas.drawRightString(190*mm,10*mm,f"Page {doc.page}")
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()


def offer_pdf(details, profile, reference):
    from .ivory_recurring import billing_text
    terms = details["terms"]
    if details.get("billing"):
        terms += "\n\n" + billing_text(details)
    return document(profile,title="QUOTATION",reference=reference,customer=details["customer"],email=details["email"],address=details["address"],
                    intro=details["intro"],lines=details["lines"],terms=terms)


def ivory_invoice_pdf(invoice, profile, receipt=False):
    from .quote_templates import invoice_bank_details
    d=(invoice.booking.workflow_state or {}).get("ivory_invoice_metadata",{}).get(invoice.id,{})
    return document(profile,title=("VOID INVOICE" if invoice.status == "void" else "CANCELLED INVOICE" if invoice.status == "cancelled" else "RECEIPT" if receipt else "INVOICE"),reference=invoice.number,customer=d["customer"],email=d["email"],address=d["address"],
                    intro=d["intro"],lines=[{**line,"amount":line["total"]} for line in invoice.line_items],terms=d["terms"],
                    issued=invoice.issue_date,due=invoice.due_date,paid=invoice.paid,payments=invoice.payments,invoice=True,receipt=receipt,bank=invoice_bank_details(invoice,profile))
