# BookingSystem2026 V8.37 - Growth Engine connector

This release adds the controlled two-way connector agreed for Weddings By Mark.
The booking system remains authoritative for enquiries, quotes, invoices,
payments, contracts and confirmed weddings. The Growth Engine owns proposal
engagement and sales follow-ups.

Safety properties:

- Integration and automatic sync both default to off.
- A Growth Engine outage never blocks booking work.
- Snapshot hashes and event IDs prevent duplicate processing.
- Manual Growth Engine leads use a private authenticated endpoint and never
  trigger an acknowledgement email during transfer.
- The first real payment or confirmed booking stops Growth Engine sales
  follow-ups after the snapshot is received.
- Cancellation and reopening are reflected on the same linked lead.
- A start-date filter prevents accidental import of older booking history.

No existing database columns are altered. Two small connector tables are
created automatically on startup through the existing SQLAlchemy metadata
bootstrap.
