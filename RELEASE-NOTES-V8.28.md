# BookingSystem2026 V8.28 — Workflow Clarity

Build: `2026.08.23-workflow-clarity-v8.28`

## What changed

- One factual journey stage is now used on booking lists, dashboard rows,
  search results and inside each client record.
- An accepted quote without a first payment is labelled **Quote accepted ·
  provisional**. It is not described as secured.
- A record manually marked as booked without a stored first payment is labelled
  **Payment not recorded · provisional** for safe review.
- The Today screen is split into **Needs your action** and **Waiting and
  upcoming**. A client is counted once even when several action alerts exist.
- Signed agreements awaiting your countersignature no longer appear twice.
- The next-step panel prioritises submitted forms, Final Wedding Timings,
  countersigning, overdue payments and retained failed-email review.
- The Journey opens with a compact status explanation and progress markers.
- Mobile controls remain full-sized and the new summaries collapse cleanly.

## Safety boundaries retained

- No new automatic email has been added.
- Imported Studio Ninja general communication remains paused. The only existing
  approved exception remains the eligible 30-day Final Wedding Timings invitation
  for Studio Ninja weddings after 20 October 2026.
- Testing Mode, invoice numbers, payments, Google Calendar rules, public date
  availability, Accounts settings and complete backups are unchanged.
- Deployment performs no data migration and sends no client email.

## Verification

- Python and JavaScript syntax checks pass.
- 84 cumulative regression checks are collected; all release test files pass in
  their isolated database environments.
- A clean local application start and `/api/health` smoke check were completed.
