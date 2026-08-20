# BookingSystem2026 V8.20.1 — Manual Timings Send Fix

This corrective release makes the promised manual Final Wedding Timings email
available from every eligible wedding's Journey screen.

- An open form shows **Send timings form now**.
- A form that is not yet open shows **Open without emailing** and
  **Open & send form now**.
- A Studio Ninja import still requires the protected one-email confirmation.
- Sending this form does not remove or weaken the Studio Ninja automation lock.
- No other Studio Ninja email, reminder or portal action is enabled.
- The Journey renderer removes stale copies, so the timings panel appears once.

Build: `2026.08.20-manual-timings-send-fix-v8.20.1`

No compose, environment or manual database change is required. Deployment does
not send an email. The button sends only after the administrator confirms it.
