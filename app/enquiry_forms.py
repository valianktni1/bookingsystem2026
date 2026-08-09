from copy import deepcopy

from fastapi import HTTPException


PROTECTED_ENQUIRY_FIELDS = {
    "primary_first_name", "partner_first_name", "email", "event_date",
    "location", "heard_about_us", "privacy_agreed",
}

BUILT_IN_ENQUIRY_FIELDS = PROTECTED_ENQUIRY_FIELDS | {
    "phone", "package_interest", "selfie_booth_interest", "message",
    "promo_code", "fun_answer",
}

BUILT_IN_TYPES = {
    "primary_first_name": "text", "partner_first_name": "text", "email": "email",
    "phone": "tel", "event_date": "date", "location": "venue",
    "package_interest": "package", "selfie_booth_interest": "select",
    "message": "textarea", "promo_code": "text", "heard_about_us": "select",
    "fun_answer": "text", "privacy_agreed": "checkbox",
}


DEFAULT_ENQUIRY_FORM = {
    "heading": "Please fill in your details and let the countdown to your best day ever begin!",
    "introduction": "I’ll check your date and come back to you as soon as possible.",
    "payment_title": "We have payment options for you",
    "payment_options": [
        "Option 1 — £100 deposit on booking, with the balance due 45 days before your wedding.",
        "Option 2 — £100 deposit on booking, followed by two equal payments 90 days and 45 days before your wedding.",
        "Option 3 — 25% deposit on booking, with the remaining 75% due 45 days before your wedding.",
    ],
    "submit_label": "Submit enquiry",
    "success_heading": "Thank you!",
    "success_message": "Your enquiry has landed safely. I’ll check your date and get back to you as soon as I can.",
    "fields": [
        {"id": "primary_first_name", "key": "primary_first_name", "label": "Bride's/Groom's first name", "field_type": "text", "placeholder": "Your first name", "help_text": "", "required": True, "enabled": True, "width": "half", "options": [], "custom": False},
        {"id": "email", "key": "email", "label": "Email address", "field_type": "email", "placeholder": "Enter your email", "help_text": "", "required": True, "enabled": True, "width": "half", "options": [], "custom": False},
        {"id": "partner_first_name", "key": "partner_first_name", "label": "Groom's/Bride's first name", "field_type": "text", "placeholder": "Partner's first name", "help_text": "", "required": True, "enabled": True, "width": "half", "options": [], "custom": False},
        {"id": "phone", "key": "phone", "label": "Phone number", "field_type": "tel", "placeholder": "Optional - sometimes replies go into spam", "help_text": "", "required": False, "enabled": True, "width": "half", "options": [], "custom": False},
        {"id": "event_date", "key": "event_date", "label": "Wedding or event date", "field_type": "date", "placeholder": "", "help_text": "", "required": True, "enabled": True, "width": "half", "options": [], "custom": False},
        {"id": "location", "key": "location", "label": "Wedding/event venue", "field_type": "venue", "placeholder": "Start typing your wedding venue", "help_text": "", "required": True, "enabled": True, "width": "full", "options": [], "custom": False},
        {"id": "package_interest", "key": "package_interest", "label": "Package", "field_type": "package", "placeholder": "Any particular package caught your eye?", "help_text": "", "required": False, "enabled": True, "width": "half", "options": [], "custom": False},
        {"id": "selfie_booth_interest", "key": "selfie_booth_interest", "label": "Interested in the Selfie Booth?", "field_type": "select", "placeholder": "Please choose", "help_text": "", "required": False, "enabled": True, "width": "half", "options": ["Yes please", "Maybe - tell me more", "No thank you"], "custom": False},
        {"id": "message", "key": "message", "label": "Tell me a little about your enquiry", "field_type": "textarea", "placeholder": "Enter your message", "help_text": "Maximum 5,000 characters", "required": False, "enabled": True, "width": "full", "options": [], "custom": False},
        {"id": "promo_code", "key": "promo_code", "label": "Special offer code", "field_type": "text", "placeholder": "Enter your code, if applicable", "help_text": "", "required": False, "enabled": True, "width": "half", "options": [], "custom": False},
        {"id": "heard_about_us", "key": "heard_about_us", "label": "How did you hear about Weddings By Mark?", "field_type": "select", "placeholder": "Choose an option", "help_text": "", "required": True, "enabled": True, "width": "half", "options": ["Google search", "Facebook", "Instagram", "TikTok", "Wedding venue", "Recommendation", "Previous wedding guest", "Other"], "custom": False},
        {"id": "fun_answer", "key": "fun_answer", "label": "Quick fun question: spaghetti hoops on toast or beans on toast?", "field_type": "text", "placeholder": "Answer here :) ", "help_text": "", "required": False, "enabled": True, "width": "full", "options": [], "custom": False},
        {"id": "privacy_agreed", "key": "privacy_agreed", "label": "I agree that Weddings By Mark can use these details to respond to and manage my enquiry.", "field_type": "checkbox", "placeholder": "", "help_text": "", "required": True, "enabled": True, "width": "full", "options": [], "custom": False},
    ],
}


def default_enquiry_form() -> dict:
    return deepcopy(DEFAULT_ENQUIRY_FORM)


def validate_enquiry_form(config: dict) -> dict:
    """Protect workflow fields and normalise editor input before publishing."""
    clean = deepcopy(config)
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    fields = clean.get("fields") or []
    for field in fields:
        field_id = field["id"]
        key = field["key"]
        if field_id in seen_ids or key in seen_keys:
            raise HTTPException(422, f"Each question needs a unique internal name ({key}).")
        seen_ids.add(field_id)
        seen_keys.add(key)
        field["label"] = field["label"].strip()
        field["placeholder"] = field.get("placeholder", "").strip()
        field["help_text"] = field.get("help_text", "").strip()
        field["options"] = [str(option).strip() for option in field.get("options", []) if str(option).strip()]
        if field["field_type"] == "select" and not field["options"] and field["field_type"] != "package":
            raise HTTPException(422, f"Add at least one choice to ‘{field['label']}’.")
        if key in PROTECTED_ENQUIRY_FIELDS:
            field["enabled"] = True
            field["required"] = True
            field["custom"] = False
        elif not field.get("custom") and key not in BUILT_IN_ENQUIRY_FIELDS:
            raise HTTPException(422, f"Unknown built-in question: {key}")
        elif field.get("custom") and not key.startswith("custom_"):
            raise HTTPException(422, "Custom question internal names must start with custom_ followed by a unique id.")
        if not field.get("custom") and BUILT_IN_TYPES.get(key) != field["field_type"]:
            raise HTTPException(422, f"The field type for ‘{field['label']}’ is protected.")
    missing = PROTECTED_ENQUIRY_FIELDS - seen_keys
    if missing:
        raise HTTPException(422, "Essential questions cannot be removed: " + ", ".join(sorted(missing)))
    clean["payment_options"] = [str(option).strip() for option in clean.get("payment_options", []) if str(option).strip()]
    return clean


def public_enquiry_form(config: dict) -> dict:
    clean = deepcopy(config)
    clean["fields"] = [field for field in clean.get("fields", []) if field.get("enabled", True)]
    for field in clean["fields"]:
        field["protected"] = field["key"] in PROTECTED_ENQUIRY_FIELDS
    return clean


def validate_enquiry_answers(config: dict, core_answers: dict, custom_answers: dict) -> tuple[dict, list[dict]]:
    """Validate published custom questions and snapshot all visible answers."""
    accepted_custom: dict = {}
    snapshot: list[dict] = []
    for field in public_enquiry_form(config).get("fields", []):
        key = field["key"]
        value = custom_answers.get(key) if field.get("custom") else core_answers.get(key)
        empty = value is None or value == "" or value == [] or value is False
        if field.get("required") and empty:
            raise HTTPException(422, f"Please answer ‘{field['label']}’.")
        if field.get("custom"):
            if isinstance(value, str):
                value = value.strip()[:5000]
            if field["field_type"] == "select" and value not in (None, "") and value not in field.get("options", []):
                raise HTTPException(422, f"Please choose a valid answer for ‘{field['label']}’.")
            accepted_custom[key] = value
        snapshot.append({
            "key": key,
            "label": field["label"],
            "field_type": field["field_type"],
            "answer": value,
            "custom": bool(field.get("custom")),
        })
    return accepted_custom, snapshot
