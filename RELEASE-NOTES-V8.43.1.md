# Booking V8.43.1 — Growth planning on the corrected V8.42.1 base

Uses the supplied BookingSystem2026-V8.42.1-complete(1).zip as the authoritative base. Preserves the setMode dashboard hotfix and its browser cache marker, nonblocking dashboard, shared mailbox cache and scan locks, mobile Emails workspace, and batched evidence queries.

Adds the pending Growth planning connector: up to 732 inclusive days of availability, authenticated yearly/monthly confirmed wedding totals independent of the enquiry cutoff, and first quote-send, acceptance and booking-fee dates in the existing batched evidence path.

All JavaScript and mailbox service files are unchanged from the supplied ZIP. No password, Compose, invoice, contract or email-sending configuration changes.

Pair with Growth V1.4.1. Use scripts/deploy-v141-paired.sh from this paired package; it now checks for Booking V8.43.1. Supersedes the undelivered-to-server V8.43 package.
