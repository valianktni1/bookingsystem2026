# Ivory quotes and invoices - V8.88

Open **Ivory quotes & invoices** from the menu (More on a phone).

## Andy's first invoice

Choose **Prepare Andy's agreed invoice**. Select his existing Ivory project, if present; otherwise enter his billing email to create a project. The three agreed lines total £1,649. The opening payment is £599.50, received 19 October 2026; the remaining balance is £1,049.50. Check the customer details and save the draft, then view **Invoice preview**. Choose **Record agreement & create invoice**, record Andy's agreement, and create the invoice. This uses the next shared WBM number and records the earlier payment once. No email is sent until you deliberately choose **Email invoice** and send it.

Ivory bank details must be saved in Business settings before invoicing. The bank details and billing details are frozen with the invoice. The issuer, logo and document design remain Ivory Digital. Existing numbered invoices and payments are not migrated or renumbered.

## Future quotes

Use **Service templates** for reusable service descriptions, included items, one-off prices and separately billed monthly services. Templates can be edited without changing earlier quotes. Save a draft, review its PDF and create a client acceptance link. You can copy the link or review and send a quote email in the same dialog. Acceptance creates one invoice; repeating acceptance returns the same invoice. Generating a link or loading a page never sends mail.

Revise an unaccepted quote with a reason: the old version is retained and its acceptance link stops working. After acceptance, use **Quote additional services** on the same project. Its invoice contains only the extra work and starts with no opening payment; the original invoice and payment stay intact. Reductions or cancellations of an already issued invoice still require deliberate invoice/credit handling rather than silently replacing its agreed figures. Monthly services are shown separately and are not automatically charged or included in the one-off invoice.

## Deployment and scope

The release adds one table, `ivory_offers`, and a settings record for templates. No live customer, invoice or payment is created at startup. Future WBM and Ivory invoices share the existing WBM allocator with a database lock and collision checks. Existing imported invoices keep their existing rendering. Native Ivory invoices created by this workspace use the new layout.

Validation: isolated API tests cover invoice/payment creation, retries, quote revisions and invalidated links, selected versus optional/monthly items, bank snapshots, shared number allocation, preview without allocation, and rejection of wedding projects. Browser tests exercise admin and client forms at 320px, 390px and 1280px in light/dark admin themes. PDFs are rendered for visual inspection and checked for searchable totals and payment dates.
