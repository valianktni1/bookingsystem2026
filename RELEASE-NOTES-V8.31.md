# BookingSystem2026 V8.31

Build: `2026.08.27-email-opening-v8.31`

## Customer email opening and secure-link evidence

- Every new customer-facing HTML email sent from a booking receives a unique opaque tracking token.
- The booking records the first and latest image load plus the total load count.
- Secure account links carry the same per-message token and record first/latest access plus visit count.
- Enquiry acknowledgements, quote emails, booking confirmations, payment receipts, signed-agreement messages, reminders, check-ins, Email Centre messages and booking-linked Inbox replies are covered.
- Email history and the desktop/mobile couple conversation show the evidence directly beside the exact message.
- The interface uses honest wording: an image load is shown as **Opened (images loaded)**, while **Link accessed** is treated as stronger evidence.
- Historical emails remain visible and are labelled as not having open tracking.
- No IP address, user agent, device identity or location is stored by the tracker.
- Existing Studio Ninja automation restrictions are unchanged.

## Safe migration

The startup migration only adds nullable timestamps, integer counters and the optional Inbox-reply link to existing tables. No booking, invoice, document, form, contract, payment, email wording or historic communication is deleted or rewritten.
