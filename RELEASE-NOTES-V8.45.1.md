# BookingSystem2026 V8.45.1 — Edit a Sent Quote

This small cumulative hotfix restores the missing quote-editing control for a
couple whose quote has been sent but not yet accepted.

## What changes

- Journey shows **Edit quote** beside **✓ Sent** while the couple is still
  deciding.
- The existing required-extra and private-discount screen opens with the saved
  choices and amounts already filled in.
- Saving updates the same secure quote link the couple already received.
- Saving sends no email and creates no invoice.
- A complimentary album can be recorded by selecting **Wedding album offer**
  and changing its amount to **£0.00**.
- The quote and generated invoice remain locked immediately after acceptance.

## Safety

- No database migration is required.
- Deployment sends no emails.
- No invoice numbers, payments, existing accepted quotes, documents, reminders,
  Google Calendar events or Accounts integration settings are changed.
- Includes every earlier V8.45 and V8.44 feature.
