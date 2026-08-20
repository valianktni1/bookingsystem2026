# BookingSystem2026 V8.18 — Thirty-day Wedding Check-in

V8.18 adds the second pre-wedding check-in requested for Weddings By Mark.

## What changes

- A confirmed or in-progress native WBM wedding receives one automatic email
  exactly 30 days before its wedding date.
- The new `Wedding check-in - 30 days before` template is visible and fully
  editable in Communications → Email templates.
- `{final_call_date}` inserts the actual Monday before that wedding. For a
  Monday wedding, the previous Monday is used rather than the wedding day.
- Mark can make the wording inactive without affecting other reminders.

## What remains unchanged

- The friendly 120-day check-in continues as before.
- The private final-details telephone task remains due 30 days before the
  wedding.
- Imported Studio Ninja records remain permanently protected from automation.
- Cancelled and archived weddings receive nothing.
- Testing Mode keeps redirecting test-record emails to Mark.
- Deployment itself sends no email.

Build: `2026.08.20-thirty-day-check-in-v8.18`
