# V8.40 — Invoice viewing and manual invoice email

Invoice previews now load PDF bytes using the administrator's authenticated session before handing them to the browser PDF viewer. A missing session shows the sign-in screen instead of opening a raw authentication error. Mobile users have an Open PDF option, and invoice/receipt downloads also fetch authenticated bytes. Invoice endpoints remain private.

Finance invoice cards and the invoice register now have Email invoice. The compose dialog shows the actual recipient and exact PDF filename, with editable subject and message. Sending attaches the selected invoice, including its current amendments and payments, using the existing business SMTP account. The send is logged in email history and audit history.

Studio Ninja imports allow an explicitly confirmed one-off invoice email. Their automatic communication remains paused. Closed invoices/cancelled bookings cannot be sent; other communication-paused records retain their block. Test bookings use the configured test recipient. SMTP errors are reported without claiming success.

Includes V8.39 Growth intelligence integration and all earlier source changes. No password, deployment configuration or database schema changes.

Deploy: copy this folder's contents into the existing Booking GitHub Desktop checkout, commit and push main. Keep the existing TrueNAS Dockge compose.yaml and .env. From /mnt/apps/dockge/data/bookingsystem2026, run:

    sudo docker compose build --no-cache app && sudo docker compose up -d --no-deps app

Refresh the browser after startup. Health build: 2026.09.07-invoice-email-v8.40.

Validation: focused invoice, email, backup and Growth connector tests; JavaScript syntax checks. Real Samsung-browser PDF rendering and live Docker deployment must be checked on the installed app. Test sends use a mocked SMTP transport; no client email was sent during development.
