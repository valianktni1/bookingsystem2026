"""Read-only allocation of recorded payments for API and PDF display."""
from decimal import Decimal
from .models import Invoice


def allocated_schedule(invoice: Invoice) -> list[dict]:
    paid_left = Decimal(invoice.paid or 0)
    result = []
    for original in invoice.payment_schedule or []:
        item = dict(original)
        amount = Decimal(str(item.get("amount") or 0))
        applied = min(amount, max(Decimal("0"), paid_left))
        paid_left -= applied
        item["paid"] = float(applied)
        item["balance"] = float(max(Decimal("0"), amount - applied))
        item["status"] = "paid" if applied >= amount else "part_paid" if applied > 0 else "scheduled"
        result.append(item)
    return result

