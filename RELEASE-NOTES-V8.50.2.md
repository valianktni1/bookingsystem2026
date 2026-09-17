# BookingSystem2026 V8.50.2 - Workflow cleanup

V8.50.2 removes two bits of friction that did not match Mark's real wedding
workflow.

## Home dashboard

- Removes the **Final-detail calls** section from Home.
- Keeps Upcoming Weddings as the practical view of coming work.
- Keeps the private Final Call Pack inside every booking.
- Dates the private telephone task for the Monday immediately before the wedding,
  including the previous Monday when the wedding itself is on a Monday.

## Completing a wedding

- **Mark wedding complete** now uses one clear confirmation.
- Delivery, album and balance tracking never block completion.
- The wedding leaves Upcoming Weddings and remains under All bookings.
- Invoices, payments, forms, agreements, emails, files and notes are retained.
- Any unfinished tracking items are recorded privately in the completion audit.
- **Reopen completed wedding** remains available if completion was accidental.

## Safety

- Deployment sends no email or SMS.
- Completion sends no email or SMS.
- No booking, invoice, payment or document is deleted or archived.
- No database migration is introduced.
- Calendar, Accounts and Growth integrations are unchanged.
