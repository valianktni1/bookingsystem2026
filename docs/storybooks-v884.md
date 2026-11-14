# Wedding storybooks · V8.84

- Every WBM wedding package shows the optional storybook at the top of its extras. Couples can also find it in their secure overview. Requests do not alter the package or quote.
- /storybook-order is a public mobile-friendly form. It supports gifts, past and future weddings, split venues, hair colour, dedication and separate personalisation per child. Identical copies use quantity. Requests are saved before confirmation and Mark's notification is queued with the existing enquiry email worker.
- Storybooks in navigation shows standalone and linked requests. Wedding overview shows requests linked to that wedding. Review the billing details and delivery recipient separately; confirm details and timing before making the invoice.
- Each order has a separate WBM invoice, using the shared numbering, PDF, email preview and payment tools. It records £34.99 per copy, including UK delivery. Only the book line and amount go on the invoice. For a linked order, the payment goes against the book sale, without changing the wedding deposit, date, invoice, package, calendar, gallery or planner.
- Paid is taken from the invoice balance. Record full payment and save the delivery recipient and address before marking sent to print. Then mark dispatched. The book text is locked after print; the delivery address can still be edited.

## Deploy

Back up first and build the pinned release with the deployment script. The app adds the storybook_orders table during startup. The existing invoice and booking tables retain their schema. Existing photography forms and WordPress page copy are unchanged by this rollout. Verify /storybook-order loads before turning on WPCode snippet #10131. The switch replaces only the old form widget when the new embedded form is ready. Disable the snippet to restore the original form.

The repository is private. The deployment script can be saved locally from GitHub while signed in; the Docker build uses a repository read token when needed. Never paste the token into chat or add it to compose.yaml.

## Local checks

Run tests/test_v884_storybooks.py and tests/test_v883_enquiry_response.py separately. SMTP is mocked; all records are temporary. The browser test tests package placement, prefilled details, validation, multiple children and phone widths with intercepted requests.
