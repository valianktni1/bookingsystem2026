# BookingSystem2026 V8.31.1

Build: `2026.08.28-enquiry-date-clash-v8.31.1`

## Enquiry date-clash protection

- A website enquiry is checked against existing Weddings By Mark wedding dates as soon as it is received.
- If that date already has a confirmed or in-progress wedding, **DATE BOOKED** appears in New Enquiries.
- The matching wedding also shows that an open enquiry exists for its date.
- Opening either record displays a prominent private **DATE CLASH WARNING** banner.
- Multiple live enquiries for the same date are also identified before either quote is sent.
- Secured archived weddings continue to protect their date, matching the public availability check's safety-first behaviour.
- Cancelled weddings, completed records, Testing Mode, archived enquiries and Ivory Digital projects do not create warnings.

## Clear expired-session message

If Mark's 12-hour booking-system session expires during an action, open modals now close and the full sign-in screen explains that the booking-system session expired and nothing was sent. This is separate from the Hostinger email account connection.

## Safety

The warning is private to the admin system. It sends no email, changes no booking, and does not affect the public date checker, Google Calendar, payments, Accounts, or Studio Ninja automation protection.
