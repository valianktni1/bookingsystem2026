# BookingSystem2026 V8.24 — Dashboard & Combined 30-Day Email

Build: `2026.08.22-dashboard-timings-email-v8.24`

## What changed

- **Upcoming Weddings is now near the top:** it appears immediately below the
  Today heading, before the action queues.
- **Only genuine upcoming booked weddings appear:** enquiries, cancellations and
  Ivory Digital projects are excluded, and the weddings are ordered by date.
- **One combined 30-day email:** the friendly check-in and Final Wedding Timings
  request remain one automatic email rather than two separate messages.
- **Easy-to-find editable template:** under Email Templates it is named
  **30-day check-in & Final Wedding Timings**. Both its subject and body can be
  edited.
- **Direct form button:** the email includes a prominent
  **COMPLETE YOUR FINAL WEDDING TIMINGS** button opening the correct form.
- **Saved wording protected:** existing edits—including the around-6pm telephone
  call wording—are not reset by deployment or restart.

## Safety retained

- Studio Ninja imports still have general automation suppressed.
- The only approved imported-booking automatic communication remains the Final
  Wedding Timings invitation for eligible weddings after 20 October 2026.
- No invoice, payment, Google Calendar, Accounts, package, form-answer or booking
  data is changed.
- All V8.23.2 mobile submission and V8.23.1 complete-backup fixes are retained.

No YAML, environment-variable or database migration change is required.
