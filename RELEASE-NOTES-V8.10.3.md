# BookingSystem2026 V8.10.3

Build: `2026.08.18-workflow-assurance-v8.10.3`

This cumulative release makes the live booking journey easier to verify and completes
the wedding agreement bilaterally.

## What changes

- New BookingSystem agreements are automatically countersigned as **Mark Adam Powell**
  immediately after the couple accepts them.
- The couple receives a warm confirmation email with their secure agreement link.
- A native agreement accepted before this update displays a one-time countersign button
  in **Forms & agreement**.
- The admin booking shows persistent delivery proof for the initial quote, booking
  confirmation, latest payment confirmation and completed-agreement email.
- Invoices and agreements open in an in-app PDF viewer on desktop and mobile; Download
  remains available.
- The client portal shows both parties' names and signed dates.
- Invoice PDFs no longer display a Studio Ninja reference. The private source reference
  remains retained internally for audit and migration safety.

## Safety boundary

- No deployment-time emails are sent.
- No historical agreement is backfilled or altered.
- Imported Studio Ninja agreements cannot be countersigned by the new endpoint.
- Imported bookings remain visible, with their existing automation suppression unchanged.
- Invoice numbers, payments, cancellations, reminders, portal links and Accounts sync
  settings are not changed by this release.

## Verification

- 28 automated tests pass.
- Python modules compile successfully.
- All changed JavaScript files pass syntax validation.
