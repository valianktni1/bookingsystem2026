# BookingSystem2026 V8.28.1 — Public Enquiry Embed Hotfix

Build: `2026.08.24-enquiry-embed-hotfix-v8.28.1`

## Cause found

The V8.27 browser-security update added `X-Frame-Options: DENY` to every page.
That was correct for the private booking system, but it also prevented the
public `/enquiry` form from loading inside the iframe on
`perfectweddingsbymark.uk`. The visible result was
`booking.weddingsbymark.uk refused to connect`.

## Correction

- The public `/enquiry` document now uses a precise Content Security Policy
  allowing it to be framed only by:
  - `https://perfectweddingsbymark.uk`
  - `https://www.perfectweddingsbymark.uk`
- Private admin pages, client records, invoices and all other routes retain
  `X-Frame-Options: DENY`.
- The full V8.28 workflow-clarity update remains included.
- Deployment sends no email and changes no booking, invoice, payment, Calendar
  or Accounts data.

## Verification

- Added an automated check proving `/enquiry` has the restricted frame allow
  list while `/dashboard` remains `DENY`.
- Python and JavaScript syntax checks pass.
- Clean local server and health endpoint smoke tests pass.
