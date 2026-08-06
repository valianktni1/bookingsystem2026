# BookingSystem2026 V8.9.3 - Agreed Payment Date UI Fix

This is a complete cumulative deployment containing every feature through V8.9.3.

## Corrected

- The invoice panel now displays **Final payment due** and **Change final payment date** after the V8.2 safety interface has loaded.
- The control is available on any non-void invoice with an outstanding balance, including protected Studio Ninja imports.
- Imported invoices remain protected from deletion and historical alteration; only the agreed final payment date can be changed deliberately.
- The main payment register identifies manually agreed dates instead of describing them as the normal 45-day date.

## Existing agreed-date behaviour retained

- The normal date remains 45 days before the wedding until Mark agrees an exception.
- The exception applies only to that couple and does not change their wedding date.
- The invoice card, register, generated PDF and payment reminders use the agreed date.
- A private reason is retained in the audit log.

## Safety

- No database schema change is required.
- Existing bookings, Studio Ninja records, documents, payments and invoice numbers are preserved.
- Deployment sends no emails and changes no existing payment dates.
- Imported records remain permanently automation-suppressed.
- Live WBM and Ivory Digital invoice counters are unchanged.
