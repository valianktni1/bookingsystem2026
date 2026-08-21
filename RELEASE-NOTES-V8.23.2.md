# BookingSystem2026 V8.23.2 — Final Timings Mobile Fix

## Incident confirmed

The affected client page and JavaScript loaded successfully, but the server logs
contained no `POST /api/client/.../forms` request when the couple pressed the final
button. Mobile browser validation was stopping submission before the request left
the phone.

## Corrected

- Submission uses explicit five-step validation instead of silent native form
  blocking.
- Any incomplete required answer opens its exact step, receives focus and shows a
  clear visible message.
- The couple's current answers, confirmation and step survive a refresh within the
  same browser session.
- The submit button changes to `Sending securely…` and is disabled while sending.
- Double presses cannot create duplicate requests.
- Failed network/server requests retain the draft and show an error.
- The draft is cleared only after the server confirms successful submission.
- Updated asset versions force phones to load the corrected JavaScript and CSS.

## Safety

- No database migration or environment change.
- No automatic email is introduced.
- No booking, invoice, payment, agreement, Calendar or Accounts logic is changed.
- Studio Ninja automation suppression and its existing Final Timings exception are
  unchanged.
