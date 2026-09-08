# BookingSystem2026 V8.42

## Faster dashboard

- Today renders from the booking database first and never waits for live IMAP.
- New email replies are merged into the visible queues quietly after the mailbox answers.
- A 60-second header-only cache and one scan lock per brand prevent overlapping mailbox scans.
- The Inbox refresh button still performs a deliberate fresh check.

## Direct couple email workspace

- Every booking has a clear **Emails** section on desktop and mobile.
- Sent, opened and secure-link counts are visible at the top.
- The retained booking-system email history appears immediately.
- The complete matched Hostinger conversation loads below without holding up the rest of the record.
- The main couple **Emails** quick action opens this history in one tap; **Write email** remains inside it.

## Growth integration

- Communication evidence is read in three bounded database queries rather than repeatedly per booking.
- Growth V1.3/V8.41 availability, payload fields, authentication and retry behaviour are unchanged.

No database migration or Compose change is required. No email is sent by deployment.
