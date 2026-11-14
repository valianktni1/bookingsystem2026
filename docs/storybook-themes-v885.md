# Storybook themes
The existing storybook enquiry URL now offers Wedding Storybook, Christmas Wedding, Christmas Adventure and Holiday Adventure. Wedding details are only required for wedding themes; an optional destination is available for Holiday Adventure. One theme applies to each request, with separate personalisation for each child. Make a separate request for a different theme.

The classic wedding book stays £34.99 per copy. Other themes are enquiries with price and delivery confirmed manually. An admin must enter the agreed price per copy before invoicing. The invoice records the theme, unit price and quantity; totals come from the saved invoice once issued. Existing requests without a theme continue as Wedding Storybook. No database schema change or WordPress switch is needed.

Paid orders can export a Markdown design brief for manual production. It omits buyer contact, billing, delivery and payment details. This release does not add automatic artwork generation, print-ready templates or a Lulu connection.

Deploy with DEPLOY-V8.85.sh. The main photography enquiry route, payment logic and WordPress integration are unchanged.
