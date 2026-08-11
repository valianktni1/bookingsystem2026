# BookingSystem2026 V8.9.8

Complete cumulative release built on V8.9.7.

## Wedding Booking Form builder

- New **Wedding Booking Form** editor under Setup.
- Edit headings, introductions, step wording, question wording, help text, required status and order.
- Add, edit, hide and delete custom questions.
- Essential workflow fields remain protected so bookings and invoices cannot be broken accidentally.
- Existing submitted answers remain stored against their booking.

## Payment-plan automation

The Wedding Booking Form now asks the couple to select one payment plan:

1. Package booking fee, then the balance 45 days before the wedding.
2. Package booking fee, then two equal payments 90 and 45 days before the wedding.
3. 25% within one day, then 75% 45 days before the wedding.

The accepted quote invoice is updated automatically. Its number, total, line items and any payments already recorded are retained. Payments are allocated oldest instalment first, and the Payments register shows the next unpaid date. Original Studio Ninja invoices and schedules are never recalculated.

## Safe Testing Mode

- Highly visible switch in the top bar.
- New website enquiries created while enabled are permanently marked **TEST**.
- Every client-facing email for those records is locked to the nominated test address.
- Turning Testing Mode off does not remove that safety lock from existing test records.
- Existing live bookings and imported Studio Ninja records are never changed by the switch.
- Completed test journeys, including simulated payments, can be removed using the existing deliberate permanent-delete confirmation.
- Real bookings with payment history remain protected from permanent deletion.

## Safety and compatibility

- Additive database migration only (`bookings.is_test` plus a new settings table).
- No live invoice counter reset.
- No Google Calendar integration.
- Imported Studio Ninja communication suppression remains intact.
- Existing agreed final-payment-date overrides remain supported.

Automated verification: **15 tests passed**.
