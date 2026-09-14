# BookingSystem2026 V8.48 — exceptional payment arrangements

## What Mark can now do

- Open a native accepted wedding and choose **Payments**.
- Press **Secure by special agreement** when payment has genuinely been agreed
  for a later date.
- Record the agreed payment date and a mandatory private reason.
- Keep payment reminders paused for that arrangement (the safe default), while
  normal 120-day and 30-day wedding check-ins continue.
- Remove the arrangement deliberately if circumstances change.

## Safety and truthfulness

- No fake deposit or Payment row is created.
- The booking, Google Calendar and public date checker all treat the date as
  secured only while the audited arrangement is active.
- The invoice clearly says that no payment has been received and shows the
  individually agreed payment date.
- Activating or removing the arrangement sends no client email.
- A genuine payment ends the exception automatically but preserves its history.
- If that only payment is deleted as a correction, the arrangement is restored
  automatically so the date does not silently become available.
- Removing the exception restores its earlier invoice dates and provisional
  booking state. Fields changed later are preserved rather than overwritten.
- Studio Ninja imports, Testing Mode records, cancelled jobs and completed jobs
  cannot use this control.
- V8.47.1 Growth planning and V8.47 website revenue attribution remain included.

No database migration is required; the audited record uses the existing
`workflow_state` JSON field.
