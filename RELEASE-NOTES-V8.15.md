# BookingSystem2026 V8.15 — Couple Payment Reference

V8.15 replaces the client-facing invoice-number payment reference for native
Weddings By Mark bookings with a recognisable reference made from both first
names and the wedding date.

Example:

`Beth Nixon & Stuart Turner · 15 May 2027` becomes **BETHSTUART150527**.

## Where it appears

- the package-selection/quote screen before acceptance;
- the confirmed-package screen after acceptance;
- the client invoice and payments screen;
- the downloadable Weddings By Mark invoice PDF;
- the initial quote email;
- the package-accepted email;
- booking-fee and active final-balance reminder emails.

The reference is prominently bold in the email and invoice wording. A native
wedding uses the same reference for every payment. Long names are shortened
safely so the complete reference remains within the common UK 18-character
bank-reference limit while retaining recognisable parts of both first names.

## Safety and compatibility

- Invoice numbers and the invoice counter are unchanged.
- Existing invoices, payments, bookings and database rows are not rewritten.
- Imported Studio Ninja records keep their existing invoice-number reference.
- Ivory Digital records keep their existing reference behaviour.
- No emails are sent during deployment.
- Google Calendar, public availability, Accounts integration and complete
  backup behaviour are unchanged.
- No database migration, YAML change or environment change is required.

Build: `2026.08.19-couple-payment-reference-v8.15`
