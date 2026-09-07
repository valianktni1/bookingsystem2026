# Booking V8.39 — Growth activity evidence

Paired with Growth V1.2.0. Adds original enquiry date, recorded sent-email and quote-link timestamps, accepted/payment state and a bounded read-only scan of recent inbox headers to Growth snapshots.

Mailbox metadata is kept in a separate table, so a background scan does not change the booking's edited date. Sync works when the mailbox is unavailable, preserving previously observed incoming timestamps. Each sync prioritises records least recently synchronised so a large backlog progresses.

No client emails are sent by this connector. No credentials or catalogue values are modified. See the paired Growth release notes for mailbox coverage and reporting limitations.
