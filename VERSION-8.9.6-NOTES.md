# Version 8.9.6 — Unified Hostinger Inbox

This is a complete cumulative release containing every feature through V8.9.6.

## What is new

- One clean **Inbox** inside the admin system for both businesses.
- Live secure IMAP connection to `mark@perfectweddingsbymark.uk` and
  `admin@ivorydigital.uk`.
- Correct sending address is selected automatically when replying.
- Replies preserve normal email thread headers.
- Sent replies are retained in the booking system and copied to Hostinger's
  Sent folder where supported.
- Incoming senders are matched to their booking/project by email address.
- A matched record opens directly from the email.
- Current BookingSystem2026 clients can receive the correct secure-account
  button in a reply.
- Imported Studio Ninja clients remain manual-only and never receive a silently
  generated portal link.
- Attachments can be downloaded securely from the reader.
- Read/unread state is synchronised back to Hostinger.
- Untrusted email HTML, remote images and tracking pixels are not loaded.
- Mailbox passwords remain environment-only and are never returned to the
  browser or saved in the booking database.

## Hostinger settings

- IMAP: `imap.hostinger.com`, SSL, port `993`
- SMTP: `smtp.hostinger.com`, SSL, port `465`
- Username: the complete mailbox email address
- Password: that individual Hostinger mailbox password

The app supports separate IMAP passwords but can also reuse the existing SMTP
mailbox credentials.
