# BookingSystem2026 V8.48.1 - friendly invoice filename hotfix

## Fixed

- Invoice and receipt downloads now use the couple/project name, date and real
  invoice number instead of a temporary browser UUID.
- The mobile **Open PDF** action now opens the authenticated server document, so
  Samsung Browser's PDF viewer also receives the real filename.
- The in-app secure PDF preview remains available exactly as before.
- The same friendly filenames are returned in both the admin area and the
  couple's secure portal.

Example:

`Marnie-and-Robert-30-October-2026-WBM02519-Invoice.pdf`

The PDF itself, invoice numbering, payments, emailed attachments, Accounts sync,
reminders and Google Calendar are unchanged. No database migration is required.
