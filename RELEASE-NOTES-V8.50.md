# BookingSystem2026 V8.50 — Stability and UK-time safety

V8.50 is deliberately a protective release. It does not redesign Mark's live
workflow and it does not automatically enable any communication.

## What changed

- The shared Weddings By Mark awards panel now contains the approved organised
  layout, including County Brides Winner 2026 and Nominated 2027. The same
  central asset is used by branded emails, mailbox replies, previews and PDFs.
- The supplied 1.7 MB artwork has been carefully reduced to approximately
  146 KB at 1020 × 680, preserving the approved appearance while keeping email
  downloads sensible.
- Background client emails and automatic SMS can run only between 09:00 and
  19:00 in `Europe/London`.
- British Summer Time is handled automatically.
- Manual email and SMS actions remain available outside that window.
- Quote follow-up dates use the UK date on which the quote email was sent.
- SMS settings visibly show the protected delivery window.
- The former example administrator password is explicitly rejected in
  production.
- A fresh empty installation now seeds Platinum at £1,350 and Ultimate at
  £1,799. Existing live package records are not changed.

## Preserved safety boundaries

- `SMS_AUTOMATIC_ENABLED` remains `false` by default.
- All seven automatic SMS templates remain inactive by default.
- TEST bookings remain restricted to `SMS_TEST_NUMBER`.
- Studio Ninja imports remain protected from automation.
- SMS remains excluded from Accounts and Growth.
- Existing bookings, quotes, invoice numbers, payments, files, contracts,
  forms, Google Calendar events and counters are untouched.
- No database schema migration is introduced.

## Deployment behaviour

Building or starting V8.50 sends no client email or SMS. The ordinary database
backup should still be taken before deployment. Do not turn on automatic SMS
until The SMS Works reply number, test number and secured webhooks have all been
verified from a TEST booking.
