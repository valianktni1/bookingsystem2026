# Phase 2B release notes

## Client portal

Each booking or project can generate a 90-day private link. The client can complete their booking/project form, submit final wedding details and accept the current agreement. Links are random, stored as hashes and can expire.

Agreement acceptance permanently records the exact title, version and wording accepted, plus the supplied name/email, timestamp, IP address and browser audit information. Previously accepted wording is not changed when a template is edited later.

## Communication

Brand-specific email templates are editable under Templates & Email. Available variables include `{client_first_name}`, `{portal_url}`, `{event_date}`, `{package_name}`, `{quoted_total}`, `{deposit_amount}` and `{balance_due_date}`.

SMTP credentials remain environment-only. Add them to the Dockge YAML; never commit the password to GitHub.

## Reminders

When explicitly enabled, the app checks every six hours for balance reminders exactly 14 and 7 days before the balance due date, and final-detail questionnaires 30 days before a wedding. A reminder log prevents duplicate sends for the same booking and day.

Automatic reminders are disabled by default until SMTP has been tested.
