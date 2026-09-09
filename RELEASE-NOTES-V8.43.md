# BookingSystem2026 V8.43

## Individual quote follow-up controls

- Adds separate **Pause/Resume** controls for the next-day quote follow-up and final nine-day check.
- Pausing one never pauses the other.
- Payment reminders, questionnaires, agreements and wedding check-ins are unaffected.
- Controls show whether each email is Active, Paused, Sent, Not needed or waiting for the quote.
- A control becomes read-only once its email has sent or the couple accepts the quote.
- Each change is retained in the private booking activity history.
- The existing two standard messages remain editable and labelled Automatic under Email Templates.

The controls are stored safely in the existing booking workflow record. No database migration or Compose change is required, and deployment sends no email.
