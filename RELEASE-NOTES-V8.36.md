# BookingSystem2026 V8.36 — Private Owner Progress Notifications

Build: `2026.09.05-owner-progress-notifications-v8.36`

This is a cumulative release and includes every BookingSystem2026 feature
through V8.35.

## New private alerts for Mark

BookingSystem2026 now sends a private branded email to the existing
`ADMIN_EMAIL` address when a couple:

- accepts a quote;
- submits or updates the Wedding Booking Form/questionnaire;
- submits or updates the Final Wedding Timings Form; or
- signs the wedding agreement.

Each alert identifies the couple, wedding date and venue, contains a direct
link to the relevant private booking section, and sets Reply-To to the couple's
email address. This makes it quick to open their record, watch for the booking
fee and reply personally when needed.

## Today screen and safe delivery

- Recent quote acceptances and completed agreements appear in **New client
  updates** on Today for 48 hours.
- Submitted forms remain in New client updates until Mark records that they
  have been reviewed.
- A private alert is attempted only after the couple's action has been safely
  committed. An email failure can never undo an accepted quote, submitted form
  or signed agreement.
- Failed alerts appear as private notifications in **Communication problems**
  and can be deliberately retried.
- The four alert templates are editable under Email Templates and an individual
  alert can be disabled by making its template inactive.

## Privacy protection

- Owner notification logs and templates are excluded from the couple's portal,
  email history and client-email template selectors.
- No alert uses a client tracking pixel.
- Testing Mode redirects private alerts to the selected test mailbox.
- No new Compose setting or database migration is required. The current
  `ADMIN_EMAIL` and Weddings By Mark SMTP settings are reused.

## Existing features retained

- V8.35 manual holidays/date blocks, public Booked result and Google Calendar
  block syncing.
- V8.34 protected accepted-invoice amendments while a balance remains due.
- V8.33.2 streaming complete backup.
- V8.33.1 Final Wedding Timings PDF download.

