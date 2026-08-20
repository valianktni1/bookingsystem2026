# BookingSystem2026 V8.19 - Dashboard Payment Total

V8.19 adds the requested at-a-glance money total to the Today dashboard.

## What changes

- The Payments due soon card still shows the number of payments due.
- Directly underneath, it now shows the combined outstanding amount due within
  the next 60 days in a larger, prominent format.
- The total is calculated from the exact payment items displayed in the queue.
- Changing the business filter recalculates the total for All businesses,
  Weddings By Mark or Ivory Digital.

## What remains unchanged

- Individual payment rows and links remain as they are.
- Invoice balances, due dates and payment records are not altered.
- No reminder schedule changes.
- No client email, Google Calendar or Accounts action is triggered.

Build: `2026.08.20-dashboard-payment-total-v8.19`
