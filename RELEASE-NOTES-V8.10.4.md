# BookingSystem2026 V8.10.4

Build: `2026.08.19-full-contract-v8.10.4`

This cumulative release corrects the Weddings By Mark agreement template.

## What changes

- Replaces the shortened Rev 1.3 agreement with the complete Rev 1.4 August 2026 wording.
- Restores all 15 sections, including the complete drone clause.
- Clearly records the three-month download and retention period for galleries and guest
  QR-code uploads.
- Gives the signed PDF proper section headings and readable paragraph spacing.
- Safely upgrades the live Weddings By Mark template when the app starts.
- New acceptances retain the complete wording as an immutable agreement snapshot.

## Safety boundary

- No deployment-time client emails are sent.
- Previously signed agreements and imported Studio Ninja contracts are not changed.
- Invoice numbers, payments, reminders, portal links, Accounts integration and calendar
  data are not changed.
- Today's native agreement can be reset individually in **Forms & agreement**, allowing
  the couple to accept the corrected wording. It is then automatically countersigned as
  Mark Adam Powell and the normal completed-agreement email is sent.

## Verification

- 28 automated tests pass.
- The complete agreement contains more than 2,500 words.
- The signed agreement renders cleanly as a five-page A4 PDF.
- The PDF was rendered page by page and visually inspected.
