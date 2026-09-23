"""Reusable personal WBM quote offers and per-booking bank snapshots."""
import re
from uuid import uuid4
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .security import current_admin
from .models import AddOnOption, Brand, BusinessProfile, PackageOption, SystemSetting
from .schemas import QuotePreparationIn

PREFIX = "wbm_quote_template:"
BANK_KEY = "wbm_quote_bank_accounts"


def booking_bank_details(booking, profile):
    if booking and not getattr(booking, "legacy_source", None):
        saved = ((getattr(booking, "workflow_state", None) or {}).get("quote_preparation") or {}).get("bank_details")
        if saved is not None:
            return saved
    return profile.bank_details or {}


def capture_invoice_bank(booking, invoice):
    if booking.legacy_source or invoice.legacy_source:
        return
    workflow = booking.workflow_state or {}
    bank = (workflow.get("quote_preparation") or {}).get("bank_details")
    if bank is not None:
        booking.workflow_state = {**workflow, "invoice_bank_details": {
            **workflow.get("invoice_bank_details", {}), invoice.id: dict(bank)}}


def invoice_bank_details(invoice, profile):
    booking = invoice.booking
    if not getattr(invoice, "legacy_source", None) and not getattr(booking, "legacy_source", None):
        saved = ((getattr(booking, "workflow_state", None) or {}).get("invoice_bank_details") or {}).get(getattr(invoice, "id", None))
        if saved is not None:
            return saved
    return profile.bank_details or {}


def accounts(db):
    row = db.get(SystemSetting, BANK_KEY)
    if row:
        return row.value["accounts"]
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == Brand.WBM))
    bank = (profile.bank_details or {}) if profile else {}
    return [dict(id="primary", label="Current account", **{k: bank.get(k) or "" for k in
                 ("account_name", "sort_code", "account_number")}),
            dict(id="alternate", label="New account", account_name="", sort_code="", account_number="")]


def bank_snapshot(db, account_id):
    bank = next((b for b in accounts(db) if b["id"] == account_id), None)
    if not bank or not all(bank.get(k) for k in ("account_name", "sort_code", "account_number")):
        raise HTTPException(422, "Complete the selected bank account in Business settings first")
    return dict(bank)


def validate_offer(db, payload):
    for field, model in (("package_ids", PackageOption), ("optional_addon_ids", AddOnOption)):
        ids = getattr(payload, field)
        if ids is None:
            continue
        if field == "package_ids" and not ids:
            raise HTTPException(422, "Choose at least one package")
        query = select(model).where(model.id.in_(ids), model.brand == Brand.WBM, model.is_active.is_(True))
        if field == "optional_addon_ids":
            query = query.where(model.is_discount.is_(False))
        if len(db.scalars(query).all()) != len(set(ids)):
            raise HTTPException(422, "A selected package or optional extra is unavailable")
    for field, discount in (("required_addons", False), ("discounts", True)):
        ids = [x.addon_id for x in getattr(payload, field)]
        rows = db.scalars(select(AddOnOption).where(AddOnOption.id.in_(ids), AddOnOption.brand == Brand.WBM,
                     AddOnOption.is_active.is_(True), AddOnOption.is_discount.is_(discount))).all() if ids else []
        if len(rows) != len(set(ids)) or len(ids) != len(set(ids)):
            raise HTTPException(422, "A required extra or discount is unavailable or repeated")
    if payload.bank_account_id:
        bank_snapshot(db, payload.bank_account_id)


class OfferTemplate(QuotePreparationIn):
    name: str = Field(min_length=1, max_length=140)
    subject: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=20000)


class BankAccount(BaseModel):
    id: str = Field(pattern="^(primary|alternate)$")
    label: str = Field(min_length=1, max_length=80)
    account_name: str = Field(max_length=160)
    sort_code: str = Field(max_length=12)
    account_number: str = Field(max_length=8)


class BankAccounts(BaseModel):
    accounts: list[BankAccount] = Field(min_length=2, max_length=2)


def register_quote_template_routes(app):
    @app.get("/api/quote-templates")
    def list_templates(_=Depends(current_admin), db: Session=Depends(get_db)):
        rows = db.scalars(select(SystemSetting).where(SystemSetting.key.startswith(PREFIX))).all()
        return sorted([dict(id=r.key[len(PREFIX):], **r.value) for r in rows], key=lambda x:x["name"].lower())

    @app.post("/api/quote-templates", status_code=201)
    def create_template(payload: OfferTemplate, _=Depends(current_admin), db: Session=Depends(get_db)):
        validate_offer(db, payload)
        template_id = str(uuid4())
        row = SystemSetting(key=PREFIX+template_id, value=payload.model_dump(mode="json"))
        db.add(row); db.commit()
        return dict(id=template_id, **row.value)

    @app.put("/api/quote-templates/{template_id}")
    def update_template(template_id: str, payload: OfferTemplate, _=Depends(current_admin), db: Session=Depends(get_db)):
        row = db.get(SystemSetting, PREFIX+template_id)
        if not row:
            raise HTTPException(404, "Quote template not found")
        validate_offer(db, payload)
        row.value = payload.model_dump(mode="json"); db.commit()
        return dict(id=template_id, **row.value)

    @app.delete("/api/quote-templates/{template_id}", status_code=204)
    def delete_template(template_id: str, _=Depends(current_admin), db: Session=Depends(get_db)):
        row = db.get(SystemSetting, PREFIX+template_id)
        if not row:
            raise HTTPException(404, "Quote template not found")
        db.delete(row); db.commit()

    @app.get("/api/quote-bank-accounts")
    def get_accounts(_=Depends(current_admin), db: Session=Depends(get_db)):
        return accounts(db)

    @app.put("/api/quote-bank-accounts")
    def save_accounts(payload: BankAccounts, _=Depends(current_admin), db: Session=Depends(get_db)):
        if {b.id for b in payload.accounts} != {"primary", "alternate"}:
            raise HTTPException(422, "Provide the current and new account")
        values = []
        for bank in payload.accounts:
            value = bank.model_dump()
            value["sort_code"] = re.sub(r"[ -]", "", value["sort_code"])
            if any(value[k] for k in ("account_name", "sort_code", "account_number")):
                if not value["account_name"].strip() or not re.fullmatch(r"\d{6}", value["sort_code"]) or not re.fullmatch(r"\d{8}", value["account_number"]):
                    raise HTTPException(422, "Enter an account name, six-digit sort code and eight-digit account number")
                value["sort_code"] = "-".join(value["sort_code"][i:i+2] for i in (0,2,4))
            values.append(value)
        row = db.get(SystemSetting, BANK_KEY)
        if row is None:
            row=SystemSetting(key=BANK_KEY); db.add(row)
        row.value={"accounts":values}; db.commit()
        return values
