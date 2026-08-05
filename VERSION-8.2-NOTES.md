# BookingSystem2026 — Version 8.2

## Safe Cancellation, Voiding and Deletion

Version 8.2 is a controlled update built on the deployed Version 8.1 venue-search patch.
It does not replace the booking, quote, client portal, invoice, email, document or gallery workflows.

### Booking and project controls

- Cancel a booking or project with a required reason.
- The previous status is retained so the record can later be reopened safely.
- Open workflow tasks are completed on cancellation and only those tasks are reopened later.
- Existing client portal links are revoked immediately.
- Cancelled records remain available under the existing **Cancelled** status filter.
- Cancelled records are excluded from dashboard dates, the working calendar, open tasks and automatic reminders.
- Reopening requires a reason and does not reactivate old portal links.

### Invoice controls

- Void an invoice while retaining its original number, PDF, notes and payment history.
- A void invoice has a £0.00 outstanding balance and is excluded from dashboard totals and reminders.
- Void PDFs are clearly headed **VOID INVOICE** and state that no payment is due.
- Only a genuinely mistaken, unpaid invoice with no payment and no accepted-quote link can be deleted.
- Invoice numbers are never reused.

### Agreements and submitted forms

- Reset an incorrect agreement acceptance with a required reason.
- Reset a Wedding Booking Form or Final Questionnaire so a corrected copy can be submitted.
- The corresponding workflow task is reopened.
- The main agreement template is not deleted or overwritten.

### Permanent deletion

Permanent record deletion is intended for tests, duplicates, accidental records and spam.
It requires a reason and an exact typed confirmation using the record title.

The system removes removable linked data and stored documents, including tasks, notes, quotes,
unpaid invoices, portal links, submitted forms, agreement acceptance, email logs and reminders.
A final non-client-identifying audit entry records that an administrator performed the deletion.

Permanent deletion is blocked when the record contains payment history or a void/retained invoice.
Normal client cancellations should be cancelled and then archived, not permanently deleted.

### Database and deployment safety

- No destructive database migration is included.
- Existing records are not changed during deployment.
- Version 8.2 uses existing status and JSON fields.
- New controls run only when the administrator deliberately selects an action and confirms it.
