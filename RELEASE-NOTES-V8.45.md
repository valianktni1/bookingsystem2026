# BookingSystem2026 V8.45 — Everyday Workflows

V8.45 builds directly on the V8.44 stable workspace foundation. It fills the
main day-to-day gaps without changing invoice numbering, stored payments,
documents, accepted quote snapshots or signed agreement evidence.

## Close an unsuccessful enquiry

- Open enquiries and unaccepted quotes have a clear **Close enquiry** action.
- Mark records a useful private outcome: booked elsewhere, no response, date
  unavailable, budget, plans changed or another reason.
- The record moves to Archived, its open link is revoked, automatic messages are
  paused and its private tasks are closed.
- **Reopen enquiry** restores its earlier status, automation setting and tasks.
- No client email is sent and financial history is never altered.

## Move a booked wedding date safely

- Confirmed and in-progress weddings have a dedicated **Move wedding date** action.
- The proposed date is checked for other enquiries, weddings and private date blocks.
- The same booking, invoice numbers, payments, documents and signed agreement
  snapshot are retained.
- Live invoice supply/payment dates, future reminder dates, the private final-call
  task and Google Calendar event move with the wedding.
- An individually agreed final payment date is preserved.
- Signed paperwork is not rewritten; a private review task is created when needed.
- The old date, new date and reason are retained in Activity. No client email is sent.

## Form and agreement chasing

- When the Wedding Booking Form is outstanding, Journey offers a dedicated
  review-and-send form reminder.
- Once the form is received but the agreement is outstanding, Journey offers a
  separate agreement reminder.
- Mark sees and can edit the subject and message before sending.
- These reminders are one-off manual actions, not new automatic messages.

## Reply-aware quote follow-up

- Before a next-day quote check becomes due, the reminder runner performs one
  cached, header-only inbox check.
- If the exact client address has genuinely replied since the quote, only the
  next-day check is paused automatically.
- The final nine-day check remains independent and can still be left active or
  paused by Mark.
- If the mailbox is unavailable, the established reminder runner continues; the
  booking system is never held up by Hostinger.

## Deployment safety

- No database schema migration is required.
- Deployment sends no emails.
- Accounts integration remains off unless separately enabled.
- V8.45 includes all V8.44 workspace/navigation fixes.
