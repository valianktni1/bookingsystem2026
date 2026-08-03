# Mark's Business Studio — Phase 2B

Phase 2B of Mark's private, self-hosted booking and business management system. It adds secure client forms, electronic agreement acceptance, editable email templates, SMTP sending and reminders to the Phase 2A record, workflow, document and invoice tools.

## Included in Phase 2A

- Secure single-administrator login with an HTTP-only session cookie
- Responsive Teal Operations interface for desktop, tablet and mobile
- Separate Weddings By Mark and Ivory Digital business profiles
- Wedding booking and digital project records
- Contact information, dates, venue/project, packages, values and notes
- Automatic starter workflow tasks for each new record
- Task completion and dashboard workflow health
- Bank-transfer invoice records with one shared chronological counter
- Brand-aware invoice numbers: `WBM02001`, `ID02002`, and so on
- PDF, DOCX, JPEG and PNG document uploads against the correct record
- Audit trail foundation for logins, records, tasks, invoices and uploads
- Studio Ninja migration fields ready for a later preview/import tool
- Data model ready for forms, contracts, email automation and gallery integration
- Fully editable records and contact details
- Functional status filters and reversible record archiving
- Add, edit, complete and delete workflow tasks
- Timestamped private notes and activity history
- Upload, download and delete record documents
- Branded PDF invoices and downloadable receipts
- Bank-transfer payment history for deposits, part-payments and balances
- Editable Weddings By Mark and Ivory Digital invoice identities and bank details
- Safe additive startup migrations that preserve existing Phase 1 PostgreSQL data
- Expiring secure client portal links
- Wedding booking form and final-details questionnaire
- Ivory Digital project information form
- Editable brand-specific email and agreement templates
- Electronic agreement acceptance with versioned wording, timestamp and audit details
- SMTP sending from individual records
- Automatic final-balance reminders 10 days before, one day before and two days after the due date
- Submitted forms automatically complete their matching workflow tasks
- Editable Weddings By Mark package and add-on catalogue
- Client pick-and-choose quotes with live mobile totals and eligibility rules
- Accepted quote snapshots that preserve the original wording and price
- Automatic numbered invoice creation when a client accepts a package
- Package and add-on line items on invoice PDFs
- Supplied Weddings By Mark contract wording without the example client's personal details
- Supplied Wedding Booking Form fields in the secure client portal
- Responsive WordPress/Elementor enquiry iframe at `/enquiry`
- Website enquiries automatically create booking records and workflow tasks
- Copyable auto-resizing iframe embed code in Packages & pricing
- One-click initial quote email with a wedding booking link that opens directly on package selection
- Secure client invoice and receipt downloads inside the same booking portal
- Automatic package-accepted and invoice-ready email when SMTP is configured
- Separate Weddings By Mark and Ivory Digital Hostinger SMTP identities and readiness indicators
- Responsive HTML email stationery with the correct embedded logo for each business
- Matching logo and gold-accent branding on invoice and receipt PDFs
- Weddings By Mark award badges on photography emails and invoices only
- Immediate branded website-enquiry notification to `mark@perfectweddingsbymark.uk`
- New-enquiry notifications include all submitted details and reply directly to the couple

Studio Ninja import and gallery automation remain planned for later phases without restructuring the core data.

## TrueNAS deployment

The supplied `compose.yaml` is already configured for:

- Public application port: `30049`
- App/database data: `/mnt/apps/bookingapp2026/data/postgres`
- Booking documents: `/mnt/temp-tntermediate/bookingapp2026data/data`
- Intended domain: `booking.weddingsbymark.uk`

### 1. Prepare the project

Copy `.env.example` to `.env` and edit every value marked `replace-...`.

Use a long random `SESSION_SECRET`, a unique database password and a strong administrator password. The email address in `ADMIN_EMAIL` becomes the first administrator account on the first launch.

### 2. Deploy in Dockge

Add the repository or upload this project to the Dockge stack directory, then start it with Docker Compose. The database is private to the stack; only port `30049` is exposed.

### 3. Nginx Proxy Manager

Create a Proxy Host:

- Domain: `booking.weddingsbymark.uk`
- Scheme: `http`
- Forward host/IP: your TrueNAS server's internal IP address
- Forward port: `30049`
- Websockets: enabled
- Block common exploits: enabled
- SSL: request/assign the certificate, enable Force SSL and HTTP/2

### 4. First sign-in

Open `https://booking.weddingsbymark.uk` and sign in with `ADMIN_EMAIL` and `ADMIN_PASSWORD` from `.env`.

The first startup creates:

- The administrator account
- Weddings By Mark profile with invoice prefix `WBM`
- Ivory Digital profile with invoice prefix `ID`
- Shared invoice counter starting at `2000`

The first invoice therefore becomes `WBM02001` or `ID02001`, depending on its brand. The numeric sequence is shared, so the next invoice always advances globally.

## Safe updates

From the stack directory:

```bash
docker compose down
docker compose build --no-cache app
docker compose up -d
```

Do not remove either mounted dataset during updates. Back up both datasets before major upgrades.

## Health check

The unauthenticated container health endpoint is:

```text
/api/health
```

It returns Phase `2B` plus SMTP/reminder configuration status when the application is running.

After both SMTP mailboxes have been tested successfully, enable automatic reminder scanning in
Dockge with `REMINDERS_ENABLED: "true"`. The scanner runs every six hours by default and records
each scheduled message so it cannot send the same reminder twice.

## Development and tests

Use Python 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

Tests cover authentication, record editing, notes/activity, workflows, shared cross-brand numbering,
fixed wedding payment dates, all three balance-reminder timings, payments, branded PDF invoices and
receipts, document upload, archiving, business settings, dashboard totals and logout.

## Later-phase candidates

- Studio Ninja export preview, matching and complete migration
- Calendar and availability controls
- Gallery creation and status automation
- Two-factor authentication and configurable backup/export tools
