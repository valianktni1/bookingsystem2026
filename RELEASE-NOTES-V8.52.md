# BookingSystem2026 V8.52 — Custom Workflow Builder

V8.52 completes the second half of Workflow Studio: photographers and
videographers can now build additional client journeys without changing code.

## Editable email signature and artwork

Business Settings now includes a proper email-signature editor for each
business. The wording can be changed without editing every email template, and
the business logo and awards badge/panel can each be shown or hidden.

PNG and JPEG replacements can be uploaded directly from the same screen. They
are validated, limited to 3MB, stored in the existing backed-up application
storage and embedded inside outgoing emails so recipients do not have to load
images from an external website. Template previews and test emails use the same
saved signature and artwork as live messages.

Weddings By Mark starts with Mark's contact signature, the existing Weddings
By Mark logo and the approved smaller centred awards panel already selected.
Existing email templates and sending rules are not changed.

## Build a workflow

**＋ Add workflow** opens one guided form containing:

- a clear private workflow name;
- one of nine triggers: enquiry received, quote sent, quote accepted, booking
  form received, agreement signed, booking fee received, booking-fee due date,
  final-balance due date, or wedding date;
- a before/after direction where the trigger permits it;
- a timing from zero to 365 days;
- Automatic, Review first, or Task only action;
- an existing client email template or a new template created directly inside
  the builder.

Every workflow starts as **Draft**. Its email can be previewed and test-sent to
the administrator before the workflow is activated.

## Activation safety

The default activation choice is **New bookings only**. Bookings created before
activation cannot enter that workflow, even if its trigger date would otherwise
make it due.

**Include current eligible bookings** is a separate warned option with a second
confirmation. It is useful when intentionally adding a step to current work but
cannot happen accidentally.

Active workflows cannot be edited or deleted. They must first be paused. Paused
and draft workflows can be edited, duplicated or safely deleted. Sent email,
audit and reminder history is never removed.

## Existing safeguards

- Studio Ninja imports never enter custom workflows.
- Cancelled, archived or communication-paused bookings remain excluded.
- Quote-sent workflows stop after quote acceptance.
- Enquiry workflows stop once the booking progresses.
- Paid booking fees and balances stop obsolete payment workflows.
- Payment arrangements continue to pause relevant reminders.
- Client-specific Review first previews and daytime automation rules remain.
- V8.51 built-in workflow settings remain unchanged.
- SMS automation is not changed.
- One safe additive database column is created automatically at startup; there
  is no manual migration command and no new environment variable is required.
