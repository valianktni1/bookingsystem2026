# BookingSystem2026 V8.10 — Accounts Link

This cumulative release adds a controlled, one-way financial link to Weddings By Mark Accounts V1.3.

## What is transferred

- Genuine Weddings By Mark wedding invoices only.
- Accepted/confirmed jobs; enquiries and unaccepted quotes are excluded.
- Exact invoice numbers, itemised charges, payment dates and signed refund entries.
- Cancellation date/reason and the resulting zero balance.
- Existing Studio Ninja imports that fall within the agreed accounting scope.

## Safety controls

- Nothing is sent unless the accounts receiver is enabled with the same private key.
- The initial transfer is manual and requires an exact confirmation phrase.
- Automatic synchronisation is a separate setting and defaults to off.
- Content-hashed event IDs prevent duplicated invoices or payments.
- A failed accounts request never blocks booking work.
- The link sends no emails, creates no client portal links and contacts no calendars.
- Ivory Digital, web-design, test, enquiry and quoted records are excluded.

The booking system remains the source of truth. Linked copies in the accounts app are read-only.
