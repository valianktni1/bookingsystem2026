# BookingSystem2026 V8.11

Build: `2026.08.19-navigation-workflow-v8.11`

## Proper browser navigation

- Dashboard, enquiries, weddings, calendar, invoices and every other workspace
  now have their own refresh-safe address.
- Every client section has a stable address such as
  `/bookings/{client-id}/journey` or `/bookings/{client-id}/payments`.
- Browser Back and Forward restore the previous workspace, client and section.
- Search, status filter, archived selection, business filter and page scroll
  are retained with the history entry.

## Today screen

The dashboard is now a working day rather than a collection of totals. It shows:

- New enquiries to review and quote.
- Sent quotes awaiting acceptance.
- Accepted quotes awaiting the first payment.
- Wedding Booking Forms and agreements still outstanding.
- Payments due within 14 days and overdue payments.
- Private final-detail telephone calls due soon.

Each item opens the correct client and section. Actions such as preparing a
quote, recording a payment or countersigning an agreement open the existing
confirmation control; V8.11 never automatically confirms or sends anything.

## Simpler client workspace

The record is reduced from six overlapping sections to five:

1. Overview
2. Journey
3. Payments
4. Files
5. Activity

Journey combines quote/email controls with the Wedding Booking Form and
agreement in their real order. Activity combines private notes with one
chronological history, including successful or failed email delivery.

## Global search and clearer status

- Search now finds clients by name, email, telephone, venue or package and
  invoices by current or legacy number from any workspace.
- Active and archived results are included.
- Recently updated clients appear when the search box is first selected.
- The visible client status follows the real journey: New enquiry, Quote sent,
  Quote accepted, Secured, Booking details complete, Ready for wedding and
  Completed. Stored database status values remain unchanged.

## Safety

- No database schema migration.
- No automatic message, quote, reminder, portal link or client action.
- No change to invoices, payments, invoice counters or Accounts integration.
- Imported Studio Ninja records remain manual-communication-only.
- Testing Mode, cancellation, permanent-deletion and void controls remain in
  their existing protected layers.
- The full inherited test suite and new V8.11 tests pass: **33 tests**.

