# V8.78: focused personal booking workflow

This release changes the admin presentation for native WBM wedding records.
It retains the existing save/send/sign/review/payment handlers and all server
eligibility rules. Protected imports and Ivory Digital projects keep their
established record layout. No data migration or bulk update is required.

- A compact phone header keeps occasional help in More and gives the current
  action prominence. Contact, appearance and other actions remain available.
- Pending native enquiries show the original saved message on Overview. All
  answers opens the existing read-only source view. Missing sources are stated;
  current booking details are never invented as an original enquiry.
- Quote and Paperwork are separate navigation choices. Paperwork offers Booking
  form & agreement, Final timings and Final call. These move/hide existing
  panels, retaining their handlers, locks and deep-link/review actions.
- Named quote templates show a package/price/account summary. Customise this
  quote retains the full package, extras, discount and bank controls. Fields are
  still collected by the existing code; Save quote & review email saves only,
  and the existing Send button is still required for email delivery.
- Recent-message buttons open the exact selected message. Native conversations
  show the newest messages first. Received messages can open the existing Inbox
  reply screen; no reply is sent by navigation.
- Sent EmailLog and MailboxReply queries take the latest bounded rows instead
  of the oldest rows. The API keeps chronological output and the same booking,
  recipient, owner-notification and status restrictions. Long conversations
  remain bounded; the UI directs users to Inbox for older mail.

Only navigation-pane choices are stored in sessionStorage (bounded to 50 saved
IDs). No enquiry answers or email contents are stored there by this feature.
Quotes, discounts, banks, invoice/PDF formats, automation rules and live records
are not rewritten. V8.77 bank-details and stray-newline fixes are included.

## Validation and deployment

Tests use disposable databases and intercepted browser requests. The browser
regression covers exact-message navigation, reply-controller targeting, separate
panes and reveal shortcuts, template summary/customisation, unchanged quote-save
payload and explicit fake sending. It checks native and protected records,
320/390/768/1280px widths and both themes. API tests cover long histories,
privacy scope, protected records, threaded replies, quote bank snapshots,
accepted invoice/PDF agreement, sent-quote amendments and read-only previews.

DEPLOY-V8.78.sh verifies a database backup, preserves a rollback image, builds
pinned runtime source, checks imports/assets and restarts only app. It prints a
rollback command before the build and after health checks. Refresh the browser
after success. No planner update or feature-enable switch is needed.
