from copy import deepcopy

from fastapi import HTTPException


PAYMENT_PLANS = [
    {
        "code": "standard",
        "label": "Booking fee on booking, with the balance due 45 days before the wedding",
        "description": "The package booking fee is due within one day of accepting the quote.",
    },
    {
        "code": "split",
        "label": "Booking fee on booking, followed by two equal payments",
        "description": "The two remaining payments are due 90 days and 45 days before the wedding.",
    },
    {
        "code": "quarter",
        "label": "25% on booking, with the remaining 75% due 45 days before the wedding",
        "description": "The first 25% is due within one day of accepting the quote.",
    },
]

ESSENTIAL_FIELDS = {
    "primary_full_name", "primary_phone", "primary_email", "partner_full_name",
    "street_address", "town", "county", "postcode", "wedding_date",
    "ceremony_time", "ceremony_details", "reception_details", "package_selected",
    "payment_plan",
}

FIELD_TYPES = {
    "primary_full_name": "text", "primary_phone": "tel", "primary_email": "email",
    "partner_full_name": "text", "partner_phone": "tel", "partner_email": "email",
    "street_address": "text", "town": "text", "county": "text", "postcode": "text",
    "wedding_date": "date", "ceremony_time": "time", "venue_display": "venue",
    "ceremony_details": "textarea", "reception_details": "textarea",
    "package_selected": "package", "payment_plan": "payment_plan",
    "wedding_party_size": "number", "unique_events": "textarea",
    "guest_uploads": "select", "additional_information": "textarea",
    "highlight_music": "textarea",
}


def _field(key, label, field_type, step, required=False, width="half", placeholder="", help_text="", options=None):
    return {"id": key, "key": key, "label": label, "field_type": field_type,
            "step": step, "required": required, "enabled": True, "width": width,
            "placeholder": placeholder, "help_text": help_text, "options": options or [],
            "custom": False}


DEFAULT_BOOKING_FORM = {
    "heading": "Wedding Booking Form",
    "introduction": "Three short steps to securely save all the details I need for your wedding.",
    "submit_label": "Save Wedding Booking Form",
    "success_message": "Your Wedding Booking Form has been saved securely.",
    "steps": [
        {"id": "about", "title": "About you both", "introduction": "Your names and contact details."},
        {"id": "wedding", "title": "Your wedding day", "introduction": "Confirm the date, venue and ceremony details."},
        {"id": "planning", "title": "Package, payment and planning", "introduction": "Choose your payment plan and add the final planning details."},
    ],
    "payment_plans": PAYMENT_PLANS,
    "fields": [
        _field("primary_full_name", "Bride's/Groom's full name", "text", "about", True),
        _field("primary_phone", "Bride's/Groom's phone number", "tel", "about", True),
        _field("primary_email", "Bride's/Groom's email", "email", "about", True),
        _field("partner_full_name", "Groom's/Bride's full name", "text", "about", True),
        _field("partner_phone", "Groom's/Bride's phone number", "tel", "about"),
        _field("partner_email", "Groom's/Bride's email", "email", "about"),
        _field("street_address", "Street address", "text", "about", True, "full"),
        _field("town", "Town", "text", "about", True),
        _field("county", "City/County", "text", "about", True),
        _field("postcode", "Postcode", "text", "about", True),
        _field("wedding_date", "Date of wedding/event", "date", "wedding", True),
        _field("ceremony_time", "Ceremony/service time", "time", "wedding", True),
        _field("venue_display", "Wedding venue", "venue", "wedding", False, "full"),
        _field("ceremony_details", "Exact ceremony details and venue(s)", "textarea", "wedding", True, "full"),
        _field("reception_details", "Exact reception venue details", "textarea", "wedding", True, "full", "If this is the same as the ceremony venue, please say so"),
        _field("package_selected", "Package selected", "package", "planning", True, "full"),
        _field("payment_plan", "Choose your payment plan", "payment_plan", "planning", True, "full", help_text="Your invoice and payment dates update automatically from this choice."),
        _field("wedding_party_size", "How many people will be in your wedding party?", "number", "planning", True),
        _field("unique_events", "Are there any unique events happening that I need to know about?", "textarea", "planning", True, "full", "For example, the bride will arrive on a horse"),
        _field("guest_uploads", "Wedding guest photo uploads - Package 2 and upwards", "select", "planning", False, "full", options=["Yes please", "No thank you"]),
        _field("additional_information", "Additional information", "textarea", "planning", False, "full"),
        _field("highlight_music", "Highlight video music choices for Gold, Platinum and Ultimate", "textarea", "planning", False, "full", "Please give two songs"),
    ],
}


def default_booking_form() -> dict:
    return deepcopy(DEFAULT_BOOKING_FORM)


def validate_booking_form(config: dict) -> dict:
    clean = deepcopy(config)
    steps = clean.get("steps") or []
    if not steps:
        raise HTTPException(422, "The booking form needs at least one step.")
    step_ids = {step["id"] for step in steps}
    if len(step_ids) != len(steps):
        raise HTTPException(422, "Each booking-form step needs a unique name.")
    seen = set()
    for field in clean.get("fields") or []:
        key = field["key"]
        if key in seen:
            raise HTTPException(422, f"Duplicate booking-form question: {key}")
        seen.add(key)
        if field.get("step") not in step_ids:
            raise HTTPException(422, f"Choose a valid step for ‘{field['label']}’.")
        field["label"] = field["label"].strip()
        field["placeholder"] = field.get("placeholder", "").strip()
        field["help_text"] = field.get("help_text", "").strip()
        field["options"] = [str(x).strip() for x in field.get("options", []) if str(x).strip()]
        if key in ESSENTIAL_FIELDS:
            field["enabled"] = True
            field["required"] = True
            field["custom"] = False
        if not field.get("custom"):
            expected = FIELD_TYPES.get(key)
            if not expected or expected != field.get("field_type"):
                raise HTTPException(422, f"The field type for ‘{field['label']}’ is protected.")
        elif not key.startswith("custom_"):
            raise HTTPException(422, "Custom booking-form questions must have a unique custom_ name.")
        if field.get("field_type") == "select" and not field["options"]:
            raise HTTPException(422, f"Add at least one choice to ‘{field['label']}’.")
    missing = ESSENTIAL_FIELDS - seen
    if missing:
        raise HTTPException(422, "Essential booking questions cannot be removed: " + ", ".join(sorted(missing)))
    codes = {plan.get("code") for plan in clean.get("payment_plans") or []}
    if codes != {"standard", "split", "quarter"}:
        raise HTTPException(422, "All three protected payment plans must remain available.")
    return clean


def public_booking_form(config: dict) -> dict:
    clean = deepcopy(config)
    clean["fields"] = [field for field in clean.get("fields", []) if field.get("enabled", True)]
    for field in clean["fields"]:
        field["protected"] = field["key"] in ESSENTIAL_FIELDS
    return clean


def validate_booking_answers(config: dict, answers: dict) -> tuple[dict, list[dict]]:
    accepted = {}
    snapshot = []
    visible = public_booking_form(config)
    valid_plans = {plan["code"] for plan in visible.get("payment_plans", [])}
    for field in visible.get("fields", []):
        key = field["key"]
        if key == "venue_display":
            continue
        value = answers.get(key)
        empty = value is None or value == "" or value == [] or value is False
        if field.get("required") and empty:
            raise HTTPException(422, f"Please answer ‘{field['label']}’.")
        if key == "payment_plan" and value not in valid_plans:
            raise HTTPException(422, "Please choose one payment plan.")
        if field.get("field_type") == "select" and value not in (None, "") and value not in field.get("options", []):
            raise HTTPException(422, f"Please choose a valid answer for ‘{field['label']}’.")
        if isinstance(value, str):
            value = value.strip()[:5000]
        accepted[key] = value
        snapshot.append({"key": key, "label": field["label"], "field_type": field["field_type"],
                         "answer": value, "custom": bool(field.get("custom"))})
    # Retain hidden venue metadata used by directions and the booking record.
    for key in ("venue_name", "venue_address", "venue_place_id", "venue_lat", "venue_lng"):
        if key in answers:
            accepted[key] = answers[key]
    return accepted, snapshot
