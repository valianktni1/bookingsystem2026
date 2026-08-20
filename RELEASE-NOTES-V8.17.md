# BookingSystem2026 V8.17 — Workflow Clarity

V8.17 improves payment planning and makes the email workflow easier to
understand and recover when a mail provider has a temporary problem.

## Sixty-day payment view

- The Today screen's Payments due soon queue now covers the next 60 days.
- Overdue payments remain in their separate urgent queue.
- This is a read-only visibility change. It does not send anything.
- Automatic payment emails retain the existing genuine schedule: seven days
  before, one day before and the established overdue reminders.
- The private final-detail telephone-call queue retains its shorter 14-day window.

## Email-template usage labels

Every email template now shows one plain-English classification:

- **Automatic** - sent by a genuine live workflow or reminder event.
- **Workflow action** - sent only after Mark presses its matching action.
- **Manual option** - sent only when deliberately chosen in Email client.
- **Inactive / Not used** - cannot currently be sent or belongs to an older workflow.

The label also explains the exact trigger, such as website enquiry received,
package accepted, payment recorded or agreement signed by both parties.

## Temporary email failure recovery

- Activity now explains Hostinger `454 4.3.0 Try again later` as a temporary
  mail-server refusal rather than a failed booking or agreement.
- When the latest signed-agreement confirmation has failed, Activity shows a
  deliberate Retry email button.
- The existing Journey retry remains available as well.
- Retrying sends only the confirmation email. It does not reset, replace or
  countersign the agreement again.

## Safety

- Deployment sends no email.
- No YAML, `.env` or manual database change is required.
- Existing bookings, invoices, payment schedules and signed agreements are not rewritten.
- Google Calendar and the public availability checker are unchanged.
- Accounts integration remains unchanged and stays off when configured off.
- Studio Ninja automation locks and Testing Mode protections remain intact.

Build: `2026.08.20-workflow-clarity-v8.17`
