# BookingSystem2026 V8.45.2 — Journey Quote Routing Hotfix

V8.45.2 corrects the final display route discovered from Mark's post-deployment
screenshot. The V8.45.1 quote edit logic was correct, but a later workspace
layer was rendering Notes & Activity inside both embedded Journey panels.

## Corrected Journey screen

- Step 1 now renders the genuine Quote, secure-link and email controls.
- A sent but unaccepted quote visibly shows **Edit quote** beside **✓ Sent**.
- Step 2 now renders the genuine Wedding Booking Form and agreement controls.
- Final Wedding Timings and the private telephone-call pack remain in the same
  Journey screen.
- New cache markers force browsers to load the corrected routing scripts.

## Quote safety

- Saving an edit sends no email and creates no invoice.
- The couple's existing secure link displays the saved extras and prices when
  opened or refreshed.
- Acceptance creates the invoice from that saved quote and then permanently
  locks the quote as before.

## Deployment safety

- No database migration is required.
- Deployment sends no emails.
- No existing booking, invoice, number, payment, document, reminder, Calendar
  event or Accounts setting is changed.
