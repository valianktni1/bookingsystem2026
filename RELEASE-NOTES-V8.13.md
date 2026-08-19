# BookingSystem2026 V8.13

Build: `2026.08.19-live-availability-v8.13`

## Live date checker

V8.13 connects the public Weddings By Mark date checker to BookingSystem2026
without removing the existing Studio Ninja/Google Apps Script check.

- `WEBSITE-DATE-CHECKER-V8.13.html` keeps the existing white, gold and celebration design.
- The two diary checks run together.
- If either diary says `Booked`, the visitor sees the existing booked message.
- The visitor sees available only when both diary checks complete successfully and say free.
- If a diary cannot be reached, the checker displays a retry message instead of a false available result.
- Past dates are not offered as available.

## Privacy and booking rules

The new read-only endpoint is:

`https://booking.weddingsbymark.uk/api/public/availability?date=YYYY-MM-DD`

It returns only one plain-text word: `Booked`, `Available` or `Unavailable`.
It cannot return names, venues, emails, prices, booking IDs or any other private
information. Responses are marked not to be cached so a newly accepted or
cancelled booking is reflected immediately.

Dates are protected by genuine Weddings By Mark weddings that are secured,
in progress, completed, or have an accepted quote. Active Studio Ninja imports
also protect their dates as an additional safeguard. Enquiries, unaccepted
quotes, cancelled records, Ivory Digital projects and Testing Mode records do not.

## Compatibility and safety

- No database migration.
- No new `.env` values.
- No Google OAuth changes.
- No email is sent.
- Existing Google Calendar events and connection tokens are untouched.
- Existing invoices, payments, forms, agreements and invoice numbering are untouched.
- The cumulative automated suite passes: **39 tests**.
