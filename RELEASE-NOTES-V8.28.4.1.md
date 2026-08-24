# BookingSystem2026 V8.28.4.1 - Inline PDF Preview Hotfix

Build: `2026.08.24-inline-pdf-hotfix-v8.28.4.1`

## Fixed

- Invoice previews now render inside the secure modal instead of showing a grey panel and broken-document icon.
- Authenticated inline PDF responses use `SAMEORIGIN` and `frame-ancestors 'self'`.

## Security preserved

- Only PDFs deliberately returned for inline preview may appear inside the booking system itself.
- Downloaded PDFs and all normal private application pages remain protected by `X-Frame-Options: DENY`.
- The public enquiry form retains its separate Weddings By Mark domain allowlist.
- Studio Ninja imports remain protected and manual-only.

## Included

- All V8.28.4 invoice preview and final telephone-call shortcuts.
- All earlier V8.28 workflow, enquiry and record-action fixes.

