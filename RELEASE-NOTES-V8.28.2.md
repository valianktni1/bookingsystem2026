# BookingSystem2026 V8.28.2 - Visible Enquiry Confirmation

Build: `2026.08.24-enquiry-confirmation-v8.28.2`

## Fixed

- After a successful website enquiry, the thank-you confirmation now stays in the visitor's current view.
- The embedded form sends a completion message to the surrounding website, which reduces the iframe height and smoothly brings it into view.
- A fixed-position fallback keeps the confirmation visible even when a website page still contains an older iframe helper.
- The success message is now an accessible live status and receives keyboard focus after submission.

## Preserved

- Enquiry creation, acknowledgement emails and administrator notifications are unchanged.
- The V8.28.1 domain-restricted enquiry embed protection remains in force.
- All private booking-system pages continue to deny iframe embedding.
- No booking, invoice, payment, calendar or email records are changed during deployment.

