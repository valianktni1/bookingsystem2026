# BookingSystem2026 V8.35 — Holidays & Blocked Dates

Build: `2026.09.03-manual-date-blocks-v8.35`

This is a cumulative release and includes the undeployed V8.34 protected
invoice-amendment work.

## What Mark can now do

- Open **Calendar** and choose **Block dates / holiday**.
- Block one day or a complete inclusive period, such as a two-week holiday.
- Keep a private label and optional private notes with the period.
- Edit or remove a block from the same Calendar screen on desktop or mobile.
- Open or retry the linked Google Calendar event when needed.

## Safety behaviour

- Every blocked day makes the public website availability endpoint return only
  `Booked`; the private label and notes are never disclosed.
- A new or existing enquiry on a blocked day shows `DATE BLOCKED` in the admin
  list and booking drawer.
- One all-day Google Calendar event covers the range. Google uses an exclusive
  event end date internally, while the date entered in BookingSystem2026 remains
  inclusive.
- Editing the block updates the same deterministic event. Removing the block
  safely removes the event, including retry handling after an uncertain Google
  response.
- No client, quote, invoice, task, payment or client email is created.
- A warning requires confirmation before a period containing an existing
  wedding or enquiry is blocked. Overlapping manual blocks are refused so the
  Calendar remains clear.
- Removed blocks remain as private audit tombstones and complete backups include
  both the database table and `registers/date-blocks.csv`.

## Existing features retained

- V8.34 protected accepted-invoice amendments while a balance remains due.
- Paid-in-full invoice edit lock.
- V8.33.2 streaming complete backup.
- V8.33.1 Final Wedding Timings PDF download.
- V8.33 direct Final Timings shortcut.

