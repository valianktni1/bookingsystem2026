# BookingSystem2026 V8.23.1 - Reliable Complete Backup

## Fixed

- The complete personal backup no longer holds one silent web request open while
  it builds every database export, PDF and uploaded document.
- Business Settings now shows the current preparation stage and percentage.
- The browser starts downloading only after the complete ZIP exists on disk.
- The prepared ZIP remains private and available for 24 hours.
- The download endpoint supports byte-range requests, so an interrupted browser
  transfer can resume from the same stable file.

## Safety preserved

- Backup contents remain complete and unchanged.
- Environment files, plaintext passwords, SMTP credentials and Google OAuth
  credentials remain excluded.
- Preparing or downloading a backup sends no emails and changes no bookings,
  invoices, payments, Calendar events or Accounts records.
- Every cumulative feature through the V8.23 Final Call Pack remains included.
- No YAML, environment or database migration change is required.
