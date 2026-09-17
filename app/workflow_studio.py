"""Configurable Weddings By Mark email workflow definitions.

The stored document contains only owner choices.  Product metadata and safe
defaults remain in code so older installations immediately retain their exact
pre-V8.51 behaviour without a database migration.
"""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy.orm import Session

from .models import SystemSetting


SETTING_KEY = "workflow_studio_wbm"
CACHE_KEY = "workflow_studio_wbm_resolved"
WORKFLOW_MODES = {"automatic", "review", "task", "off"}


WORKFLOW_DEFINITIONS: tuple[dict, ...] = (
    {"key": "quote_followup_1", "group": "Enquiry follow-up", "label": "First quote check-in",
     "description": "A friendly check that the couple received their quote.",
     "anchor": "quote_sent", "anchor_label": "quote sent", "direction": "after",
     "default_mode": "automatic", "default_days": 1},
    {"key": "quote_followup_final", "group": "Enquiry follow-up", "label": "Final quote follow-up",
     "description": "A final gentle reminder if the quote is still awaiting acceptance.",
     "anchor": "quote_sent", "anchor_label": "quote sent", "direction": "after",
     "default_mode": "automatic", "default_days": 9},
    {"key": "booking_form_reminder", "group": "Booking journey", "label": "Booking form reminder",
     "description": "Chases the Wedding Booking Form after a quote has been accepted.",
     "anchor": "quote_accepted", "anchor_label": "quote accepted", "direction": "after",
     "default_mode": "off", "default_days": 3},
    {"key": "contract_reminder", "group": "Booking journey", "label": "Agreement reminder",
     "description": "Chases the agreement after the Wedding Booking Form is received.",
     "anchor": "booking_form_submitted", "anchor_label": "booking form received", "direction": "after",
     "default_mode": "off", "default_days": 3},
    {"key": "deposit_due_1", "group": "Payments", "label": "Booking-fee reminder",
     "description": "Sent when the booking fee has not been received.",
     "anchor": "deposit_due", "anchor_label": "booking fee due", "direction": "after",
     "default_mode": "automatic", "default_days": 0},
    {"key": "balance_due_7", "group": "Payments", "label": "Early balance reminder",
     "description": "Warns the couple before their final balance is due.",
     "anchor": "balance_due", "anchor_label": "balance due", "direction": "before",
     "default_mode": "automatic", "default_days": 7},
    {"key": "balance_due_1", "group": "Payments", "label": "Final balance reminder",
     "description": "A final reminder shortly before the balance is due.",
     "anchor": "balance_due", "anchor_label": "balance due", "direction": "before",
     "default_mode": "automatic", "default_days": 1},
    {"key": "balance_overdue_2", "group": "Payments", "label": "Overdue balance follow-up",
     "description": "Starts after the due date and repeats until the balance is cleared.",
     "anchor": "balance_due", "anchor_label": "balance due", "direction": "after",
     "default_mode": "automatic", "default_days": 2, "repeatable": True,
     "default_repeat_days": 2},
    {"key": "check_in_120", "group": "Wedding preparation", "label": "Early wedding check-in",
     "description": "A friendly planning check-in before the wedding.",
     "anchor": "wedding_date", "anchor_label": "wedding", "direction": "before",
     "default_mode": "automatic", "default_days": 120},
    {"key": "check_in_30", "group": "Wedding preparation", "label": "Final timings invitation",
     "description": "Sends the combined final check-in and Final Wedding Timings invitation.",
     "anchor": "wedding_date", "anchor_label": "wedding", "direction": "before",
     "default_mode": "automatic", "default_days": 30},
)


def default_workflow_settings() -> dict:
    return {
        "version": 1,
        "rules": {
            item["key"]: {
                "mode": item["default_mode"],
                "days": item["default_days"],
                **({"repeat_days": item["default_repeat_days"]} if item.get("repeatable") else {}),
            }
            for item in WORKFLOW_DEFINITIONS
        },
    }


def workflow_settings(db: Session) -> dict:
    """Return validated settings merged over immutable safe defaults."""
    cached = db.info.get(CACHE_KEY)
    if isinstance(cached, dict):
        return deepcopy(cached)
    result = default_workflow_settings()
    row = db.get(SystemSetting, SETTING_KEY)
    stored = deepcopy(row.value) if row and isinstance(row.value, dict) else {}
    stored_rules = stored.get("rules") if isinstance(stored.get("rules"), dict) else {}
    for definition in WORKFLOW_DEFINITIONS:
        key = definition["key"]
        candidate = stored_rules.get(key)
        if not isinstance(candidate, dict):
            continue
        mode = candidate.get("mode")
        days = candidate.get("days")
        if mode in WORKFLOW_MODES:
            result["rules"][key]["mode"] = mode
        if isinstance(days, int) and not isinstance(days, bool) and 0 <= days <= 365:
            result["rules"][key]["days"] = days
        repeat_days = candidate.get("repeat_days")
        if definition.get("repeatable") and isinstance(repeat_days, int) \
                and not isinstance(repeat_days, bool) and 1 <= repeat_days <= 60:
            result["rules"][key]["repeat_days"] = repeat_days
    db.info[CACHE_KEY] = deepcopy(result)
    return result


def workflow_rule(db: Session, key: str) -> dict:
    return workflow_settings(db)["rules"].get(key, {"mode": "off", "days": 0})


def workflow_catalog(db: Session) -> list[dict]:
    settings = workflow_settings(db)
    return [
        {**definition, **settings["rules"][definition["key"]]}
        for definition in WORKFLOW_DEFINITIONS
    ]


def save_workflow_settings(db: Session, rules: dict) -> dict:
    clean = default_workflow_settings()
    allowed = {item["key"]: item for item in WORKFLOW_DEFINITIONS}
    if set(rules) != set(allowed):
        raise ValueError("Every workflow must be supplied exactly once")
    for key, definition in allowed.items():
        value = rules.get(key)
        if not isinstance(value, dict) or value.get("mode") not in WORKFLOW_MODES:
            raise ValueError(f"Invalid mode for {definition['label']}")
        days = value.get("days")
        if not isinstance(days, int) or isinstance(days, bool) or not 0 <= days <= 365:
            raise ValueError(f"Days for {definition['label']} must be between 0 and 365")
        clean["rules"][key] = {"mode": value["mode"], "days": days}
        if definition.get("repeatable"):
            repeat_days = value.get("repeat_days")
            if not isinstance(repeat_days, int) or isinstance(repeat_days, bool) \
                    or not 1 <= repeat_days <= 60:
                raise ValueError("Overdue repeat frequency must be between 1 and 60 days")
            clean["rules"][key]["repeat_days"] = repeat_days
    row = db.get(SystemSetting, SETTING_KEY)
    if row:
        row.value = clean
    else:
        db.add(SystemSetting(key=SETTING_KEY, value=clean))
    db.info[CACHE_KEY] = deepcopy(clean)
    return clean


def definition_for(key: str) -> dict | None:
    template_key = "balance_overdue_2" if key.startswith("balance_overdue_") else key
    return next((item for item in WORKFLOW_DEFINITIONS if item["key"] == template_key), None)
