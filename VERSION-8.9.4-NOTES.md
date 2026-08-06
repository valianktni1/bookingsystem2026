# BookingSystem2026 V8.9.4 - Phone Call and Email Controls

This is a complete cumulative deployment containing every feature through V8.9.4.

## One wedding questionnaire

- Couples complete one Wedding Booking Form / questionnaire after accepting their quote.
- The incorrect second final-questionnaire stage, waiting message and automated client reminder have been removed.
- Thirty days before the wedding, Mark receives a private workflow task to finalise the details by phone.
- The private task does not email the couple and does not add another form to their account.
- Any historical final-details form already retained from Studio Ninja remains visible as historical information.

## Email template controls

- Create, edit, activate, deactivate and permanently delete email templates from Email templates.
- Active custom templates appear in the email selector inside the relevant booking.
- Deleted templates do not reappear when the application restarts.
- Deleting a template used by an automated event safely pauses that particular message until a template with the same internal key exists again.

## Client account links

- Every email deliberately sent to an individual couple or client receives a fresh link to that specific account.
- The link is added automatically even when `{portal_url}` is missing from the template body.
- Templates may still use `{client_first_name}`, `{partner_first_name}`, `{booking_title}`, `{event_date}`, `{venue}`, `{portal_url}` and the other displayed placeholders.
- Admin-only notifications do not receive a client account link.

## Friendlier quote email

- The initial quote now uses Mark's warmer, personal wording.
- `VIEW YOUR FULL QUOTE HERE` is rendered as a proper branded button; the long secure URL is not shown in the HTML email.
- The plain-text email alternative retains the full URL for accessibility and compatibility.
- Bank details are populated safely from Weddings By Mark Business settings using `{bank_account_name}`, `{bank_sort_code}` and `{bank_account_number}`.
- Any custom template can create a button by writing `[CLICK HERE]({portal_url})`.

## Safety

- Existing records, payments, invoices, invoice counters and original Studio Ninja files are preserved.
- Imported Studio Ninja records remain automation-suppressed and receive no automatic emails.
- Deployment itself sends no emails.
- No destructive database migration is required.
