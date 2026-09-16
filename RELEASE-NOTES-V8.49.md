# BookingSystem2026 V8.49 - SMS centre

## What is new

- A **Text** shortcut and **Texts** booking tab work on desktop and mobile.
- Manual texts are reviewed before sending and keep their exact wording, send
  result, provider message ID, delivery state and SMS-credit estimate.
- An SMS Works virtual reply number enables two-way messaging. Incoming replies
  are matched back to the booking and add a private reply task to the dashboard.
- Failed delivery reports add a private task to check the mobile number.
- SMS templates live beside Email templates and can be edited without changing
  email wording.
- Seven optional automatic SMS types each have a separate per-couple pause.

## Safety on deployment

- `SMS_ENABLED=false` and `SMS_AUTOMATIC_ENABLED=false` by default.
- All seven automatic SMS templates are inactive by default.
- Deploying V8.49 sends no texts and sends no emails.
- The API token and webhook password live only in the private TrueNAS environment.
- TEST bookings require `SMS_TEST_NUMBER` and never use the client's saved number.
- Studio Ninja imports remain excluded from automatic SMS.
- Existing email reminders run independently and are not replaced or paused.

## Database

The normal application startup safely adds two new tables: `sms_templates` and
`sms_messages`. Existing booking, invoice, payment, email and integration data is
not rewritten.

## Provider setup

Use the JSON Web Token generated inside The SMS Works account. If using their
virtual reply number, configure these two authenticated webhook URLs:

- `https://booking.weddingsbymark.uk/api/integrations/smsworks/delivery`
- `https://booking.weddingsbymark.uk/api/integrations/smsworks/incoming`

Never commit the real token or webhook password to GitHub.
