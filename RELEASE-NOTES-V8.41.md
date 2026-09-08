# V8.41 — Growth availability planner

Adds an authenticated read-only endpoint for Growth to request up to 184 days of availability and the active WBM package catalogue. Uses the existing enabled integration and shared key. No customer names, contact information, holiday labels or notes are returned.

Confirmed/in-progress/completed WBM weddings protect dates, including archived/imported bookings and confirmed records awaiting payment entry. Testing records and cancelled weddings do not block dates. Non-deleted holiday ranges are inclusive. This conservative sales-planning endpoint does not change the existing website date checker.

Includes V8.40 invoice viewing and one-off invoice-email changes, plus V8.39 Growth activity integration. Existing email workflows, quotes, invoices, passwords, environment files and Dockge configuration are preserved. No Booking database schema changes.

Deploy with the paired V1.3.0 release instructions after pushing both repositories. Health build: 2026.09.08-growth-availability-v8.41.
