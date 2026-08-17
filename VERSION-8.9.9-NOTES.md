# BookingSystem2026 V8.9.9

This complete cumulative release adds proper cancellation accounting.

## Cancel booking & close balance

- Enter the real cancellation date and a required reason.
- The confirmation window shows the unpaid amount being closed and the payments
  being retained before anything changes.
- The booking becomes Cancelled, its outstanding balance becomes £0.00, open tasks
  are completed and existing client links are revoked.
- Invoice numbers, original totals, payments, documents, forms, agreements and
  history are never deleted.
- No cancellation email is sent. Automatic reminders also stop.

## Refunds

- A cancelled invoice with retained money has a separate **Record refund** button.
- Refund amount, date, bank reference and reason are retained permanently.
- A refund cannot exceed the payment still retained.
- The invoice shows the amount originally received, refunded and still retained.

## Financial presentation

- Cancelled invoices no longer count as outstanding income.
- Their PDFs say **CANCELLED INVOICE** and **no further payment is due**.
- The booking banner, invoice card and Payments register all show the cancellation
  record and the £0.00 balance due.

Studio Ninja communication suppression remains unchanged. Imported clients are not
emailed, reminders are not re-enabled, and invoice counters are not touched.
