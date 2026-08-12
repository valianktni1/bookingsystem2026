# BookingSystem2026 V8.9.8.1 — Travel-only required add-on correction

This is a complete cumulative release containing every feature and safeguard through V8.9.8.1.

## Corrected quote behaviour

- Every normal add-on is optional and unticked for the couple.
- Albums, extra hours, additional photographers, videographers and other extras can never be forced onto a quote.
- Travel expenses are the only add-on Mark can deliberately tick as required and locked for an individual wedding.
- A locked travel charge is included in the live total and cannot be removed by the couple.
- Private discounts remain admin-only and are applied automatically to the accepted quote and invoice.
- Quotes prepared on V8.9.8 with ordinary add-ons accidentally stored as required repair themselves after deployment; those extras return to optional choices immediately.
- The API rejects any future attempt to make a non-travel add-on required.

## Safeguards retained

- Existing invoices, payments, invoice numbers and counters are unchanged.
- Imported Studio Ninja bookings remain visible but communication-suppressed.
- No client emails, reminders, portal links or calendars are created or changed during deployment.
- All booking-form payment plans and Testing Mode behaviour from V8.9.8 remain included.

Verified with the complete automated suite: 15 tests passed.

