# BookingSystem2026 V8.50.1 - Inbox flow correction

V8.50.1 fixes the confusing case where a client address left in the main
workspace search silently hid every non-matching Inbox message, even though the
mailbox cards and navigation badge correctly reported unread mail.

## What changed

- A normal click on **Inbox** now opens the complete mailbox every time.
- Inbox searching is independent from the main client and invoice search.
- The Inbox has its own clearly labelled search for sender, address, subject or
  matched booking.
- An active Inbox search shows a prominent **Show all emails** button.
- **Open this couple in Inbox** still filters deliberately to that couple, but
  the active filter is now visible and easy to remove.
- The same behaviour is used by desktop and mobile Inbox shortcuts.

## Safety

- No email is sent during deployment.
- No mailbox message is changed, moved, deleted or marked read by this fix.
- No booking, reminder, invoice, payment, Calendar, Accounts or Growth record is
  changed.
- No database migration is introduced.
