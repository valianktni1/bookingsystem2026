# BookingSystem2026 V8.16 — Client Communication

V8.16 adds honest quote-link access reporting and a private, per-couple email
conversation inside the existing Journey screen.

## Quote-link access

- A newly sent initial quote uses a private, random access marker.
- The Journey shows whether the emailed quote link has been accessed, the first
  and latest access times, and the number of recorded accesses.
- The ordinary Preview and Copy URL does not contain the marker and cannot
  create a false client access.
- The wording deliberately says **Link accessed**, not **email read**. Security
  scanners can sometimes test links before a person opens them.
- No IP address, device details or third-party tracking service is used.
- Quotes sent before V8.16 remain visible but cannot be tracked retrospectively.

## Private couple conversation

- The Journey shows successful messages sent by BookingSystem2026.
- Replies sent through the built-in Inbox retain and show their full body.
- The correct Hostinger Sent folder also contributes messages sent outside the app.
- Incoming mail is read live from the correct WBM or Ivory Digital inbox.
- Matching uses only the booking's exact client email and, after the Wedding
  Booking Form is submitted, the exact primary and partner email addresses.
- Personal mail and other clients' messages are never included by a broad name,
  subject or partial-address search.
- Newly sent app email bodies are retained from V8.16 onward. Older delivery
  records remain visible, but their body cannot be reconstructed if it was not
  stored at the time.
- Testing Mode records do not read live mailbox conversations.

## Safety and compatibility

- The schema update is additive and runs automatically at application startup.
- Deployment itself sends no emails and does not access or change Google Calendar.
- Existing bookings, invoices, invoice numbers, payments and uploaded files are
  not rewritten.
- Studio Ninja imported records keep all existing manual-only automation locks.
- Accounts integration remains unchanged and stays off when already configured off.
- No YAML or `.env` change is required.

Build: `2026.08.20-client-communication-v8.16`
