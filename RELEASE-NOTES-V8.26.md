# BookingSystem2026 V8.26 — Same-Date Wedding Warning

Build: `2026.08.23-same-date-booking-warning-v8.26`

## What changed

The main **Wedding Bookings** table now displays a red caution symbol beside the
date of every active wedding when two or more genuine bookings share that date.
The affected rows receive a very light red background and the badge states how
many weddings are involved, such as **2 weddings**.

The warning remains accurate when searching or filtering, so searching for only
one couple does not hide the fact that another wedding shares their date.

## What counts as a clash

- Weddings By Mark records
- Wedding type
- Confirmed or in-progress
- Current and not archived
- Genuine records rather than Testing Mode

Enquiries, unaccepted quotes, cancelled weddings, completed records, archived
records and Ivory Digital projects do not create a false warning. Cancelling,
archiving or moving one of the weddings removes the warning automatically when
the list refreshes.

## Privacy and safety

- The caution marker is private to Mark's admin booking list.
- Couples never see it.
- It sends no email, reminder or notification.
- It makes no change to either booking, its status, Google Calendar, invoices,
  payments, Accounts or Studio Ninja automation suppression.
- Every V8.25 quote email review and earlier safety improvement is retained.

No YAML, environment-variable or database migration change is required.
