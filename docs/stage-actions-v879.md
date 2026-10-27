# V8.79: clearer stage actions and Payments

Native WBM enquiries keep later payment information collapsed until a quote is
accepted or financial activity exists. Accepted quotes move into completed
documents on Overview. All source views and quote controls remain accessible.

Payments leads with recording received money against an existing invoice.
Cash and bank transfer retain their current form, validations and confirmation
rules. A single payable invoice opens its existing payment form; several invoices
require a deliberate invoice choice. Header payment navigation no longer opens
New invoice when no payable invoice exists on a native record.

Create separate invoice is under Other payment actions, alongside guidance to use
Amend invoice for an accepted package. Its existing handler is retained. Paid and
closed invoice cards move into a history fold, open when none are payable. Their
PDF, receipt, refund and audit controls remain attached.

Exceptional administrative actions sit under More > Other booking actions. The
duplicate client-area shortcut is hidden; the main existing control remains.
Protected Studio Ninja navigation uses Messages, Notes and Quote & paperwork;
its finance layout, communication controls and protection rules are unchanged.

No migrations, backend workflow changes, bulk edits or planner update. Backend
change is the API release version only. No enquiries, payments or messages are
created by navigation. All write/send handlers retain explicit confirmation.

Validation: isolated Playwright fixtures cover enquiry/accepted stages, direct
payment form targeting, multiple invoice choice, missing invoice navigation,
explicit separate-invoice handler, closed history, quote save/send payload,
discounts and bank selection, imported protection and all seven sections at
320/390/768/1280px in both themes. Seven quote/bank/PDF API regressions pass.
Deploy script verifies a database dump, retains the old image for rollback,
builds a pinned source commit, preflights imports/assets and restarts app only.
