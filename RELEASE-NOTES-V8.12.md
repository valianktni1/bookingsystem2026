# BookingSystem2026 V8.12

Build: `2026.08.19-google-calendar-v8.12`

## Automatic Google Calendar workflow

- Connect Mark's Google account once from **Business settings**.
- When a native BookingSystem2026 wedding quote is accepted, or a native wedding
  is deliberately marked confirmed, the wedding is added to the primary Google
  Calendar.
- The event title visibly contains the couple names, first/main venue and ceremony
  time. It remains an all-day wedding entry so the system does not invent working
  start or finish hours.
- If the ceremony time is not known when the quote is accepted, the event says
  that it is to be confirmed. Submitting or updating the Wedding Booking Form
  updates the same event with the ceremony time.
- Changes to the wedding date, couple, venue or package update that same event.
- Cancelling a booking removes only its Google event. The cancelled booking,
  cancellation reason, invoices, payments, refunds and activity remain protected
  in BookingSystem2026.
- Reopening an eligible wedding recreates its event.

## Duplicate and communication protection

- Every booking has one stable Google event identity. A retry after a timeout
  updates that event rather than creating another one.
- Couples are never added as Google Calendar attendees. Creating, updating or
  deleting an event sends no client invitation.
- Existing Google events are left in place if the integration is disconnected.
- Imported Studio Ninja weddings and Testing Mode records are deliberately
  excluded to prevent duplicate legacy events or test-calendar clutter.

## Connection and failure safety

- The integration requests only Google's `calendar.events` permission and writes
  to the connected account's primary calendar.
- The long-lived Google refresh token is encrypted in the existing settings table;
  the Client Secret remains in the server environment and is never returned to the
  browser.
- Google failures happen only after BookingSystem2026 has safely committed its own
  booking change. A Google outage can never undo acceptance, editing, payment,
  form submission, cancellation or reopening.
- Pending work and errors appear in the Google Calendar card in Business settings.
  **Sync current bookings** retries them deliberately.
- The first bulk sync is manual because existing weddings may already have entries
  Mark created by hand.

## Compatibility

- No database schema migration.
- No change to invoice numbers, invoice counters, payments, refunds, contracts,
  client links, email templates, reminders or Accounts integration.
- Existing V8.11 Back/Forward navigation and all earlier safety controls remain.
- The inherited and V8.12 automated suite passes: **37 tests**.
