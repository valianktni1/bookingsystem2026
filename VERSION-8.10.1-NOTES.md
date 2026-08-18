# BookingSystem2026 V8.10.1 — Chronological WBM invoices

This cumulative release safely replaces the mixed Studio Ninja/WBM numbering with
one chronological Weddings By Mark sequence beginning at `WBM02001`.

## Ordering rule

1. Earliest positive payment or deposit date.
2. Original invoice issue date where no positive payment exists.
3. Stable date, creation-time, existing-number and record-ID tie breakers.

Refund entries are never treated as the first payment. All WBM invoices are kept in
the sequence, including paid, cancelled, void and consumed test numbers, so no number
is silently reused.

## Preserved data

- Invoice issue date and full payment history.
- Total, balance, status, cancellation/refund data and wedding details.
- Original Studio Ninja invoice number as a private legacy reference.
- Booking, quote, document and client relationships.

## Safety

- Dry run first; no database write occurs.
- Apply requires the dry-run SHA-256 digest and exact confirmation phrase.
- The apply is one database transaction and uses temporary numbers to avoid clashes.
- A CSV map, JSON map, database migration marker and audit event are retained.
- No emails, reminders, client links, Accounts calls or calendar calls occur.
- Automatic Accounts sync must remain off until the manual post-migration sync.
