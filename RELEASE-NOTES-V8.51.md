# BookingSystem2026 V8.51 — Custom Workflow Studio

V8.51 begins the proof-tested workflow foundation for the future Ivory Digital
SaaS product while keeping Weddings By Mark safe and unchanged by default.

## What is new

- A **Custom Workflow Studio** appears at the top of **Email & SMS templates**.
- Each client-email workflow has its own timing in days.
- Every workflow can be set to:
  - **Automatic** — sends at the configured stage without waiting.
  - **Review first** — creates a private approval item and sends nothing until
    the actual couple-specific branded email has been previewed and approved.
  - **Task only** — creates a private Things to do item and sends no email.
  - **Off** — creates nothing and sends nothing.
- The studio shows its approval queue and the next scheduled workflow actions.
- Email-template labels update to reflect the chosen live workflow mode.

## Safe deployment behaviour

V8.51 uses the existing V8.50.2 modes and timings as its defaults. Merely
deploying or opening Workflow Studio:

- does not send an email;
- does not create a task;
- does not change any booking, invoice, payment or client record;
- does not require a database migration.

The default schedule remains first quote check at one day, final quote follow-up
at nine days, booking-fee reminder on its due date, wedding check-ins at 120 and
30 days, balance reminders at seven and one day before, and overdue follow-ups
every two days. Booking-form and agreement reminders remain manual/off unless
Mark deliberately changes them.

## Existing safeguards retained

- The two quote follow-ups can still be paused separately for one couple.
- A detected genuine reply still pauses only the first quote check-in.
- Accepted quotes stop quote follow-ups.
- Payment arrangements continue to pause payment reminders.
- Paid balances and completed forms stop obsolete reminders.
- Studio Ninja imports remain protected; only the established eligible final
  30-day check-in can enter the workflow system.
- Inactive or missing email templates fail safely and remain visible for retry.
- SMS automation and SMS costs are not changed by this release.

## Proofing advice

Change one workflow at a time. **Review first** is the safest mode for trying a
new schedule with real work because the system prepares the item but cannot send
it without a second deliberate approval.
