"""Private final-call checklist, readiness summary and printable working pack."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .models import (Booking, BusinessProfile, ContractAcceptance, FormSubmission,
                     Invoice)
from .pdf import BRAND_ASSETS, MUTED, fitted_image, pounds
from .services import payment_reference


CHECKLIST_ITEMS = [
    ("contacts", "Both partners' contact details and the wedding-day contact are confirmed"),
    ("preparations", "Preparation address, access and my planned arrival time are confirmed"),
    ("ceremony", "Ceremony venue, start time and arrival plan are confirmed"),
    ("reception", "Reception venue and any travel or extra stops are confirmed"),
    ("groups", "Formal group photographs and important people are confirmed"),
    ("key_times", "Meal, speeches, cake cutting and first-dance times are confirmed"),
    ("special_details", "Surprises, restrictions, accessibility and sensitive family details are covered"),
    ("coverage", "Package coverage and any timing warning or extra time have been discussed"),
    ("account", "The invoice, payments and remaining balance have been checked"),
    ("final_questions", "The couple's final questions are answered and follow-up actions are noted"),
]
CHECKLIST_KEYS = {key for key, _ in CHECKLIST_ITEMS}


def clean_final_call_state(booking: Booking) -> dict:
    saved = dict((booking.workflow_state or {}).get("final_call_pack") or {})
    checklist = dict(saved.get("checklist") or {})
    return {
        "checklist": {key: bool(checklist.get(key)) for key, _ in CHECKLIST_ITEMS},
        "notes": str(saved.get("notes") or ""),
        "updated_at": saved.get("updated_at"),
        "updated_by": saved.get("updated_by"),
        "completed_at": saved.get("completed_at"),
        "completed_by": saved.get("completed_by"),
    }


def final_call_readiness(
    booking: Booking,
    booking_form: FormSubmission | None,
    final_timings: FormSubmission | None,
    contract: ContractAcceptance | None,
    invoices: list[Invoice],
) -> dict:
    outstanding = sum(
        max(Decimal("0"), Decimal(invoice.total or 0) - Decimal(invoice.paid or 0))
        for invoice in invoices
        if invoice.status not in ("void", "cancelled")
    )
    warnings = []
    if not booking_form:
        warnings.append("Wedding Booking Form is not available")
    if not final_timings:
        warnings.append("Final Wedding Timings have not been submitted")
    if not contract:
        warnings.append("No agreement is recorded")
    elif not contract.is_legacy_import and not contract.supplier_signed_at:
        warnings.append("The client's agreement still needs your countersignature")
    calculation = dict((final_timings.data or {}).get("_calculation") or {}) if final_timings else {}
    if calculation.get("coverage_warning"):
        warnings.append(
            f"Expected photography is over the package allowance by "
            f"{int(calculation.get('over_standard_minutes') or 0)} minutes"
        )
    if calculation.get("travel_warning"):
        warnings.append("Preparation and ceremony travel timings need checking")
    if outstanding > 0:
        warnings.append(f"{pounds(outstanding)} remains outstanding")
    return {
        "booking_form": bool(booking_form),
        "final_timings": bool(final_timings),
        "agreement": bool(contract),
        "agreement_complete": bool(contract and (
            contract.is_legacy_import or contract.supplier_signed_at
        )),
        "outstanding": float(outstanding),
        "warnings": warnings,
        "ready": not warnings,
    }


def _clean(value, fallback="Not supplied") -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if value is None or str(value).strip() == "":
        return fallback
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or fallback
    return str(value)


def _local_time(value: str | datetime | None) -> str:
    if not value:
        return "Not recorded"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(ZoneInfo("Europe/London")).strftime("%d %B %Y at %H:%M")


def final_call_pack_pdf(
    booking: Booking,
    booking_form: FormSubmission | None,
    final_timings: FormSubmission | None,
    contract: ContractAcceptance | None,
    invoices: list[Invoice],
    profile: BusinessProfile,
    state: dict,
) -> bytes:
    """Build Mark's complete private working pack for the final telephone call."""
    branding = BRAND_ASSETS.get(profile.brand)
    accent, ink, pale = branding["accent"], branding["ink"], branding["pale"]
    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=15 * mm,
        title=f"Final Call Pack - {booking.title}",
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("CallNormal", parent=styles["Normal"], fontName="Helvetica",
                            fontSize=8.2, leading=11.5, textColor=ink)
    small = ParagraphStyle("CallSmall", parent=normal, fontSize=7.2, leading=9.5,
                           textColor=MUTED)
    heading = ParagraphStyle("CallHeading", parent=styles["Title"], fontName="Helvetica-Bold",
                             fontSize=22, leading=26, textColor=ink, alignment=TA_RIGHT)
    section = ParagraphStyle("CallSection", parent=normal, fontName="Helvetica-Bold",
                             fontSize=11.5, leading=15, textColor=ink, spaceBefore=7, spaceAfter=6)
    value = ParagraphStyle("CallValue", parent=normal, fontSize=7.8, leading=10.5)
    story = []

    logo = fitted_image(branding.get("logo"), 68 * mm, 29 * mm)
    identity = [logo] if logo else [Paragraph(f"<b>{escape(profile.display_name)}</b>", normal)]
    header = Table([[identity, Paragraph("PRIVATE FINAL<br/>CALL PACK", heading)]],
                   colWidths=[99 * mm, 66 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([header, Spacer(1, 4 * mm), HRFlowable(color=accent, thickness=2), Spacer(1, 5 * mm)])

    final_values = dict(final_timings.data or {}) if final_timings else {}
    booking_values = dict(booking_form.data or {}) if booking_form else dict(booking.form_data or {})
    ceremony_time = final_values.get("ceremony_time") or booking_values.get("ceremony_time")
    ceremony_venue = (final_values.get("ceremony_venue") or booking_values.get("ceremony_details")
                      or booking.venue_or_project)
    reception = final_values.get("reception_venue") or booking_values.get("reception_details")
    summary_rows = [
        ("COUPLE", booking.title, "WEDDING DATE", booking.event_date.strftime("%d %B %Y") if booking.event_date else None),
        ("CEREMONY", ceremony_time, "PACKAGE", booking.package_name),
        ("CEREMONY VENUE", ceremony_venue, "RECEPTION", reception or ceremony_venue),
        ("PRIMARY CONTACT", f"{booking.client.email} / {_clean(booking.client.phone)}",
         "PAYMENT REFERENCE", payment_reference(booking)),
    ]
    summary = Table([
        [Paragraph(f"<b>{escape(left)}</b>", small), Paragraph(escape(_clean(left_value)), value),
         Paragraph(f"<b>{escape(right)}</b>", small), Paragraph(escape(_clean(right_value)), value)]
        for left, left_value, right, right_value in summary_rows
    ], colWidths=[29 * mm, 55 * mm, 30 * mm, 51 * mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d7dfdd")),
        ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#d7dfdd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary)

    readiness = final_call_readiness(booking, booking_form, final_timings, contract, invoices)
    story.append(Paragraph("Before the call", section))
    if readiness["warnings"]:
        warning_rows = [[Paragraph("!", normal), Paragraph(escape(text), normal)]
                        for text in readiness["warnings"]]
    else:
        warning_rows = [[Paragraph("OK", small), Paragraph("No outstanding readiness warnings", normal)]]
    warnings = Table(warning_rows, colWidths=[10 * mm, 155 * mm])
    warnings.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff8e7") if readiness["warnings"] else colors.HexColor("#eaf8f4")),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#dfc27f") if readiness["warnings"] else colors.HexColor("#a9d9ca")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(warnings)

    calculation = dict(final_values.get("_calculation") or {})
    story.append(Paragraph("Wedding-day run sheet", section))
    timeline_rows = [[Paragraph("<b>TIME</b>", small), Paragraph("<b>EVENT</b>", small), Paragraph("<b>DETAIL</b>", small)]]
    for item in calculation.get("timeline") or []:
        timeline_rows.append([
            Paragraph(escape(_clean(item.get("time"))), value),
            Paragraph(f"<b>{escape(_clean(item.get('event')))}</b>", value),
            Paragraph(escape(_clean(item.get("detail"), "")), value),
        ])
    if len(timeline_rows) == 1:
        timeline_rows.append(["-", Paragraph("Final timings not submitted", value), Paragraph("Confirm the complete running order during the call.", value)])
    timeline = Table(timeline_rows, colWidths=[23 * mm, 58 * mm, 84 * mm], repeatRows=1)
    timeline.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), pale),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d7dfdd")),
        ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#e3e8e7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(timeline)

    checklist = state.get("checklist") or {}
    story.append(Paragraph("Final telephone-call checklist", section))
    checklist_rows = [[Paragraph("[X]" if checklist.get(key) else "[ ]", small), Paragraph(escape(label), normal)]
                      for key, label in CHECKLIST_ITEMS]
    checklist_table = Table(checklist_rows, colWidths=[11 * mm, 154 * mm])
    checklist_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d7dfdd")),
        ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#e3e8e7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(checklist_table)

    story.extend([PageBreak(), Paragraph("Key details to discuss", section)])
    key_details = [
        ("Preparation", final_values.get("prep_venue") or booking_values.get("preparation_details")),
        ("Preparation notes", final_values.get("prep_notes")),
        ("Second preparation location", final_values.get("second_prep")),
        ("Additional stops or venues", final_values.get("extra_stops")),
        ("Wedding-day contact", " / ".join(filter(None, [str(final_values.get("day_contact") or ""), str(final_values.get("day_mobile") or "")]))),
        ("Venue coordinator", final_values.get("coordinator")),
        ("Formal group photographs", final_values.get("group_count")),
        ("Important details and requests", final_values.get("important_notes")),
        ("Unique events", booking_values.get("unique_events")),
        ("Additional information", booking_values.get("additional_information")),
        ("Highlight-video music", booking_values.get("highlight_music")),
        ("Guest QR uploads", booking_values.get("guest_uploads")),
    ]
    detail_table = Table([
        [Paragraph(f"<b>{escape(label)}</b>", small),
         Paragraph(escape(_clean(answer)).replace("\n", "<br/>"), value)]
        for label, answer in key_details
    ], colWidths=[53 * mm, 112 * mm])
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), pale),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d7dfdd")),
        ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#e3e8e7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(detail_table)

    story.append(Paragraph("Account and agreement", section))
    invoice_total = sum(Decimal(row.total or 0) for row in invoices if row.status not in ("void", "cancelled"))
    paid_total = sum(Decimal(row.paid or 0) for row in invoices if row.status not in ("void", "cancelled"))
    outstanding = max(Decimal("0"), invoice_total - paid_total)
    agreement_status = (
        "Original Studio Ninja agreement retained" if contract and contract.is_legacy_import else
        "Signed by both parties" if contract and contract.supplier_signed_at else
        "Client signed - your countersignature is still needed" if contract else
        "No agreement recorded"
    )
    account_rows = [
        ("Agreement", agreement_status),
        ("Active invoice total", pounds(invoice_total)),
        ("Payments recorded", pounds(paid_total)),
        ("Outstanding balance", pounds(outstanding)),
    ]
    account = Table([[Paragraph(f"<b>{escape(label)}</b>", small), Paragraph(escape(text), value)]
                     for label, text in account_rows], colWidths=[53 * mm, 112 * mm])
    account.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), pale),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d7dfdd")),
        ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#e3e8e7")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(account)

    story.append(Paragraph("Private notes from the final call", section))
    notes = state.get("notes") or "No private call notes saved yet."
    notes_box = Table([[Paragraph(escape(notes).replace("\n", "<br/>"), normal)]], colWidths=[165 * mm])
    notes_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffdf8")),
        ("BOX", (0, 0), (-1, -1), .7, colors.HexColor("#d9c18c")),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
    ]))
    story.append(notes_box)
    if state.get("completed_at"):
        story.extend([Spacer(1, 4 * mm), Paragraph(
            f"<b>Final call completed:</b> {escape(_local_time(state.get('completed_at')))} "
            f"by {escape(str(state.get('completed_by') or 'administrator'))}", normal,
        )])

    def answer_table(rows: list[tuple[str, object]]) -> Table:
        table = Table([
            [Paragraph(f"<b>{escape(label)}</b>", small),
             Paragraph(escape(_clean(answer)).replace("\n", "<br/>"), value)]
            for label, answer in rows
        ], colWidths=[58 * mm, 107 * mm], repeatRows=0)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), pale),
            ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d7dfdd")),
            ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#e3e8e7")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return table

    if booking_form or final_timings:
        story.extend([PageBreak(), Paragraph("Complete submitted client details", section)])
    if booking_form:
        snapshot = (booking.form_data or {}).get("_answer_snapshot") or []
        if snapshot:
            booking_rows = [
                (str(item.get("label") or item.get("key") or "Question"), item.get("answer"))
                for item in snapshot
            ]
        else:
            ignored = {"venue_place_id", "venue_lat", "venue_lng"}
            booking_rows = [
                (key.replace("_", " ").strip().title(), answer)
                for key, answer in booking_values.items()
                if not key.startswith("_") and key not in ignored
            ]
        story.extend([Paragraph("Wedding Booking Form - complete answers", section),
                      answer_table(booking_rows)])
    if final_timings:
        final_labels = {
            "ceremony_time": "Ceremony time", "ceremony_duration": "Ceremony duration",
            "ceremony_venue": "Ceremony venue and address", "reception_same": "Reception at the same venue",
            "reception_venue": "Reception venue and address", "prep_photos": "Preparation photographs",
            "prep_person": "Who is getting ready", "prep_venue": "Preparation venue and address",
            "travel_minutes": "Travel to ceremony", "start_choice": "Preferred photography start",
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
        final_rows = [
            (final_labels.get(key, key.replace("_", " ").title()), answer)
            for key, answer in final_values.items() if not key.startswith("_")
        ]
        story.extend([Paragraph("Final Wedding Timings - complete answers", section),
                      answer_table(final_rows)])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d7dfdd"))
        canvas.setLineWidth(.4)
        canvas.line(15 * mm, 9 * mm, A4[0] - 15 * mm, 9 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(15 * mm, 5.5 * mm, f"{profile.display_name} / Private final-call working copy")
        canvas.drawRightString(A4[0] - 15 * mm, 5.5 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
