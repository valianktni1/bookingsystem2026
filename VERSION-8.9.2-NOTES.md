# BookingSystem2026 V8.9.2 - Agreed Payment Dates

This is a safe cumulative deployment containing every feature through V8.9.

## New

- Open a wedding, choose **Payments**, then select **Change final payment date** on an outstanding invoice.
- The normal date remains 45 days before the wedding until Mark agrees an exception.
- The exception applies only to that couple.
- The invoice card, invoice register and generated PDF all show the newly agreed date.
- Balance reminders are rescheduled to 7 days before, 1 day before, 2 days after and every 2 days thereafter using the agreed date.
- A private reason can be entered and is retained in the audit log.
- The original wedding date is never changed by a payment extension.

## Safety

- No database schema change is required.
- Existing bookings, imported Studio Ninja records, documents and invoice numbers are preserved.
- Deployment sends no emails.
- Imported records remain permanently automation-suppressed.
- Live WBM and Ivory Digital invoice counters are unchanged.

## Verification

- All six regression tests pass when run in isolated test files.
- Python compilation and JavaScript syntax checks pass.

