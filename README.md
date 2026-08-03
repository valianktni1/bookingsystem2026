# Mark's Business Studio — Phase 1

Phase 1 of Mark's private, self-hosted booking and business management system. It is designed to replace the core Studio Ninja workflow gradually, while keeping Weddings By Mark and Ivory Digital inside one secure workspace.

## Included in Phase 1

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

This phase does not yet send emails, generate signed contracts, render invoice PDFs, import Studio Ninja exports or create galleries. Those capabilities can be added without restructuring the core data.

## TrueNAS deployment

The supplied `compose.yaml` is already configured for:

- Public application port: `30049`
- App/database data: `/mnt/apps/bookingapp2026/data/postgres`
- Booking documents: `/mnt/temp-tntermediate/bookingapp2026data/data`
- Intended domain: `booking.perfectweddingsbymark.uk`

### 1. Prepare the project

Copy `.env.example` to `.env` and edit every value marked `replace-...`.

Use a long random `SESSION_SECRET`, a unique database password and a strong administrator password. The email address in `ADMIN_EMAIL` becomes the first administrator account on the first launch.

### 2. Deploy in Dockge

Add the repository or upload this project to the Dockge stack directory, then start it with Docker Compose. The database is private to the stack; only port `30049` is exposed.

### 3. Nginx Proxy Manager

Create a Proxy Host:

- Domain: `booking.perfectweddingsbymark.uk`
- Scheme: `http`
- Forward host/IP: `192.168.24.10`
- Forward port: `30049`
- Websockets: enabled
- Block common exploits: enabled
- SSL: request/assign the certificate, enable Force SSL and HTTP/2

### 4. First sign-in

Open `https://booking.perfectweddingsbymark.uk` and sign in with `ADMIN_EMAIL` and `ADMIN_PASSWORD` from `.env`.

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

It returns `{"status":"ok","phase":1}` when the application is running.

## Development and tests

Use Python 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

Tests cover authentication, record creation, automatic workflows, shared cross-brand invoice numbering, document upload, dashboard totals and logout.

## Phase 2 candidates

- Editable email templates and scheduled reminders
- Booking forms and questionnaires with client-facing links
- Contract templates and electronic signatures
- Proper PDF invoices and receipts
- Studio Ninja export preview, matching and complete migration
- Calendar and availability controls
- Gallery creation and status automation
- Two-factor authentication and configurable backup/export tools

