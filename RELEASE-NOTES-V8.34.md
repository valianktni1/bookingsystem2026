# BookingSystem2026 V8.34 — Protected Invoice Amendments

Build: `2026.09.03-protected-invoice-amendments-v8.34`

## What Mark can now do

- Open an accepted couple's **Payments** screen and press **Amend invoice** while a balance remains outstanding.
- Add later-agreed wording or an extra without changing the existing invoice number.
- Add a ready-made **Complimentary extra hour** line at £0.00.
- Add a charged item with a quantity and price where something is agreed after quote acceptance.
- Edit or remove only the later amendment lines; the original accepted package and add-ons remain protected.

## Financial safeguards

- Paid-in-full, cancelled, void and imported Studio Ninja invoices cannot be amended.
- The revised total can never be lower than the amount already paid.
- A stale editor is rejected if a payment or another amendment was recorded in the meantime.
- The invoice number, issue date and existing payments never change.
- An individually agreed final payment date is preserved when the total changes.
- The accepted quote snapshot, booking value, client portal, invoice PDF and payment schedule update together.
- Every save requires a reason and writes a detailed private audit entry.
- Saving sends no client email and makes no Accounts or Google Calendar request.

## Final Timings

A manually added line containing **extra hour** is treated as an included coverage hour by the existing Final Wedding Timings checks.
