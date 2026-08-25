# BookingSystem2026 V8.28.4.2 - Client Receipt Opening Fix

Build: `2026.08.25-client-receipt-open-v8.28.4.2`

## Fixed

- A payment-confirmation email now takes the couple directly to the exact receipt it relates to.
- The receipt opens in the protected in-system PDF viewer instead of relying on a forced browser download.
- The email action is labelled **VIEW YOUR PAYMENT RECEIPT**.
- The client invoice screen now provides separate **View receipt** and **Download receipt** controls.

## Safety retained

- A receipt link remains protected by a long-lived, booking-specific secure token.
- The invoice must belong to that booking and must contain a recorded payment.
- Inline PDFs remain restricted to the booking system's own origin.
- Ordinary pages and downloaded PDFs retain the existing anti-embedding protection.
- Studio Ninja communication restrictions and all other workflow safeguards are unchanged.

