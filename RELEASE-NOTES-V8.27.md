# BookingSystem2026 V8.27 — Reliability and Safety

Build: `2026.08.23-reliability-safety-v8.27`

## The booking rule is now consistent

A native Weddings By Mark wedding is secured only when a genuine payment has
been recorded. Package selection and quote acceptance remain provisional, so an
unpaid accepted quote does not block the public date checker or create a Google
Calendar event.

If the only payment is deleted, the financial record is recalculated, the
booking returns to its appropriate provisional stage, the public date becomes
available and its Google event is removed. The booking itself is retained.

## Communication reliability

- Reminder attempts and failures are retained across restarts.
- Time-limited catch-up windows safely retry a missed scheduled run without
  releasing a backlog of old emails.
- Failed communications appear in a private dashboard queue.
- **Retry now** resends only retained wording and keeps the original failure in
  the audit history.
- An outgoing message interrupted by an app restart is marked for attention
  instead of remaining indefinitely as "sending".

Studio Ninja protection is unchanged. The only permitted Studio Ninja automatic
email remains the already-approved Final Wedding Timings invitation for eligible
weddings after 20 October 2026. No Accounts synchronisation is enabled.

## Calendar reliability

- Failed or pending native calendar work is retried in the background.
- Stable event identifiers prevent duplicate Google events after an uncertain
  timeout.
- Final Wedding Timings submissions update the ceremony time used in the event.
- Cancellation and removal of the only payment safely remove the event while
  retaining the booking record.

## Additional safeguards

- Rapid repeated submission of the same public enquiry is ignored safely.
- Enquiries are committed before slow notification delivery is attempted.
- Repeated failed admin sign-ins are temporarily rate-limited.
- Standard protective browser headers are applied.
- The container no longer trusts every proxy address by default.
- Client wording consistently explains that the first received payment secures
  the wedding date.

The migration is additive. Existing bookings, payments, invoices, documents,
templates, Google connection, Studio Ninja imports and settings are preserved.
No new secret, YAML edit or manual database migration is required.
