# Ivory Digital recurring billing — V8.89

In **Ivory quotes & invoices**, choose **New recurring invoice**, or use a service
template and choose **Recurring service billing**. Enter selected Monthly service
rates, then choose monthly, quarterly, six-monthly or annual billing. The default
period price is the monthly rates multiplied by 1, 3, 6 or 12; the editable agreed
price for the full period overrides that total, including an upfront discount.
Set the first service date and the number of days allowed for payment (0 means
due on issue). The initial date must be today or later when saving/revising.

The quote and customer acceptance page show the exact full-period price,
frequency and start date. A pure recurring quote may have no one-off charge.
Mixed quotes keep the one-off build and recurring services in separate invoices.
Previously quoted monthly services do not automatically become schedules.
Saved service templates and existing accepted quotes are not rewritten.

## Starting and managing a schedule

Saving a draft, viewing a preview or sharing a quote does not start billing.
Customer acceptance, or **Record agreement & start billing**, creates one schedule
and any invoice due now. A future-start service has no invoice number until due.
Future invoices are prepared automatically when each period starts. Open
**Recurring billing** to review PDFs, send invoice emails, manage the project and
record payments. No email, card charge, bank collection or payment record is
created by the recurring runner. An annual invoice stays unpaid until payment is
actually recorded. Existing WBM invoice numbering is used for every new invoice.

Each invoice prints its covered service period. Dates are calculated from the
original anchor: January 31 renews on February 28/29 and then March 31. A year
paid upfront produces no intermediate monthly invoices. Invoice date is the day
it is actually created; due date is that day plus the agreed payment allowance.

**Pause** stops generation. **Resume** uses the next original anchor date on or
after today, skipping paused periods. **Cancel schedule** stops future billing;
issued invoices and payments remain. Restart a cancelled service with a new
quote. **Edit future invoices** changes the price, description and terms only
for unissued periods and asks you to confirm those changes are agreed.
To change the billing interval, cancel the old schedule and agree a new quote
starting after its last invoiced period.

If a whole unissued period has elapsed while the app was offline, the schedule
is flagged for review. It does not silently create a backlog. **Create next
invoice** deliberately creates one due/missed period at a time. Archived,
cancelled, wedding and imported projects cannot generate recurring invoices.
Errors are shown on the schedule; one failing schedule does not block others.

## Data and deployment

V8.89 adds `ivory_recurring_plans` and `ivory_recurring_cycles`. Startup creates
these tables; existing invoice, payment and booking tables need no alteration.
Schedule creation is explicit; no existing customer is enrolled during deployment.
The complete backup export includes both tables and their period history.
Issued recurring invoices must be voided rather than permanently deleted, to
preserve the period and duplicate safeguards.

The runner checks every minute while the app is running. It locks each schedule
and uses a unique schedule/period constraint plus the existing shared invoice
allocator. Number allocation, period recording and invoice creation share one
transaction. Request/retry guards prevent duplicate acceptance and double-clicks.
Use `DEPLOY-V8.89.sh` for backup, pinned build, preflight, restart and rollback.

## Validation

- 35 isolated Ivory API tests, including 29 recurring cases and the existing six
  one-off/quote/numbering cases: all passed.
- 23 existing regression tests passed in separate processes: wedding invoice
  amendments, payment arrangements, templates, bank snapshots and Accounts sync.
- Form tests with mocked APIs passed for all frequencies, editable scope and
  prices, a discounted annual total, future edits, pause/resume and client acceptance.
- PDF tests verify totals, payment dates, service periods and unchanged issued
  text after future-price edits. Backup export includes schedule and period data.
- Concurrent SQLite scans, transaction rollback/retry, archived projects, missed
  periods, leap years and month-end anchors are covered. PostgreSQL row locking
  is used in production; a live PostgreSQL concurrency run was not available here.
- JavaScript syntax and whitespace checks passed. Chromium could not launch in
  this execution environment (`socket() failed: Operation not permitted`), so a
  new rendered desktop/mobile visual check could not be completed. Existing
  responsive dialog CSS is reused; the new form interactions were tested in JSDOM.

Some historical test files hard-code superseded V8.53 build/UI text. Those
assertions already disagree with the starting V8.88 source and were not rewritten
as part of recurring billing. The old test modules also assign process-global
database settings, so their behavioural suites were run in separate processes.
