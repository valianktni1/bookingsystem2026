# BookingSystem2026 V8.14 — Complete Backup

V8.14 adds a prominent **Download complete backup** card to Business settings.
It creates a dated ZIP on the computer currently using the booking system.

The archive contains:

- a typed, portable snapshot of every application database table and row;
- every uploaded client PDF, image and Word document;
- readable CSV registers for bookings, invoices and payments;
- newly rendered invoice PDFs, receipts and signed agreement PDFs;
- the running application source and dependency list for disaster recovery;
- a manifest, schema description and SHA-256 checksums.

The backup includes active, archived, cancelled, test and imported Studio Ninja
records. It is read-only: it sends no email, changes no data and contacts neither
Google Calendar nor Accounts.

The `.env` file and integration credentials are deliberately excluded. The
administrator password hash and Google OAuth connection are redacted. After a
full disaster restore, reset the admin password and reconnect Google Calendar.

Because the ZIP contains confidential client and financial data, store it in a
private, protected location.
