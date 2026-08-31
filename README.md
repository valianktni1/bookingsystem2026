# Mark's Business Studio — Version 8.33.2

Mark's private, self-hosted booking and business management system. The current
build includes every cumulative feature through V8.23.2, including browser-history
navigation, the client Email Centre, safe one-way Google Calendar syncing and a
privacy-safe live website availability check.

## Version 8.33.2 streaming complete backup

Large complete backups no longer appear frozen at 32% while every invoice,
receipt and signed agreement is regenerated. Each PDF is written directly into
the ZIP rather than accumulating the full batch in application memory, and the
Business Settings progress message advances through the current PDF number and
total. The resulting archive contents, credential exclusions and resumable
download remain unchanged.

## Version 8.33.1 Final Timings PDF download

The complete Final Wedding Timings pop-up now includes a prominent **Download
PDF** button beside Close. On mobile the download action becomes a large
full-width button, making the retained working PDF available in one tap on the
wedding day. The existing protected PDF endpoint and all automation remain
unchanged.

## Version 8.33 direct Final Wedding Timings access

Every wedding now has a prominent **Final timings** action immediately beneath
the couple's header on desktop and mobile. When submitted, it opens the complete
read-only form in one tap. Before submission it opens and scrolls to the existing
status, early-open and deliberate-send controls. The single automatic 30-day
check-in email still contains the direct client Final Wedding Timings button;
no second email is sent and no automation behaviour has changed.

## Version 8.23.2 Final Wedding Timings mobile reliability

The five-step client form no longer relies on the phone browser's silent native
validation at the final button. It checks every visible conditional question,
returns the couple to the exact step needing attention and displays a clear
message. In-progress answers and the current step are retained for the browser
session so a refresh does not send the couple back to an empty form. The final
button displays `Sending securely…`, prevents duplicate presses and retains the
draft when a network or server request fails. No booking, invoice, email,
Calendar, Accounts or Studio Ninja automation behaviour is changed.

## Version 8.23.1 reliable complete backup

The complete Business Settings backup now prepares as a background job with
visible stages and progress, rather than keeping one silent browser request open
while the database, PDFs and documents are assembled. The download begins only
when the dated ZIP is ready. The prepared file remains privately available for
24 hours and supports byte-range requests, allowing a browser to resume an
interrupted transfer. Backup contents and credential exclusions are unchanged.

## Version 8.23 complete final call pack

Every wedding Journey now ends with a private Step 5 Final Call Pack. It brings
together the couple's contact details, venues, package, submitted forms, complete
run sheet, coverage warnings, agreement and payment position. A ten-point checklist
and editable private notes can be saved during the call, and the existing final-call
task can be completed or reopened from the same panel. One current printable PDF is
retained privately in Files. The same private feature works for Studio Ninja imports
without sending any client message or lifting their automation suppression.

## Version 8.22 new client updates dashboard

Today now begins with one prominent queue for client activity that needs attention:
new Wedding Booking Form and Final Wedding Timings submissions, native agreements
signed by the client but awaiting countersignature, and unread mailbox replies
matched only to the couple's exact email addresses. Every row opens the relevant
booking section or exact email. Form updates remain until deliberately reviewed;
emails clear when read and agreements clear through the existing countersign flow.
This release introduces no new automated messages and leaves Studio Ninja's general
automation suppression unchanged.

## Version 8.21 final timings records

The Final Wedding Timings area now shows an unmistakable submitted or waiting
status with the submission time. A completed form can be viewed in full from
Journey, previewed as a professionally formatted PDF or downloaded. The PDF is
created automatically when the couple submits or updates their answers and one
current copy is retained privately in the booking's Files tab. Updates refresh
the same document and reopen the existing private review task.

## Version 8.20.1 manual timings send fix

The Final Wedding Timings panel now always provides a deliberate manual send
action. For Studio Ninja imports this sends only the selected timings email and
keeps the booking's general automation lock in place. A pre-cutoff wedding can
be opened and emailed manually without enabling any other client automation.
The panel also removes any stale copy before rendering, preventing duplicate
Final Wedding Timings sections when overlapping Journey refreshes complete.

## Version 8.20 final wedding timings

The secure client area now includes a five-step Final Wedding Timings Form that
opens 30 days before each confirmed wedding, or earlier when opened manually.
It creates a private run sheet, checks Bronze against four hours and Silver or
higher packages against eight hours, uses spare included time sensibly for
preparations, and flags genuine overruns only after the 15-minute grace period.
It never changes a package, invoice or charge automatically.

Studio Ninja imports retain their general automation lock. The sole exception
is the Final Wedding Timings invitation at 30 days, and only for weddings after
20 October 2026. Every other automatic email remains blocked unless explicitly
changed in a later version.

## Version 8.19 dashboard payment total

The Payments due soon card keeps its number of payments and now also displays a
prominent total of the outstanding amounts due during the next 60 days. The
figure is calculated from the exact payment rows shown in the queue and follows
the current All businesses, Weddings By Mark or Ivory Digital filter.

## Version 8.18 thirty-day wedding check-in

Confirmed Weddings By Mark weddings receive a second friendly automatic
check-in exactly 30 days before the wedding. Its fully editable template tells
the couple the actual Monday when Mark plans to telephone them and includes the
dynamic `{final_call_date}` placeholder. The existing 120-day check-in and
private final-details telephone task remain unchanged.

## Version 8.17 workflow clarity

The Today screen now shows every open payment due during the next 60 days,
without changing when any payment reminder is sent. The WBM template manager
labels the real workflow use of every template. Temporary Hostinger `454 4.3.0`
email refusals are explained clearly, and the latest failed signed-agreement
confirmation can be deliberately retried from Activity or Journey without
resetting or changing the protected agreement.

## Version 8.16 client communication

New quote emails use a private, self-hosted access marker so the client record
can show when that emailed link was first accessed and how many accesses were
recorded. The administrator's Preview and Copy link remains untracked. Each
client Journey also has one private conversation view containing successful
booking-system messages, replies sent from the built-in Inbox, messages sent
from the correct business mailbox, and incoming Hostinger mail from only the
couple's exact email address or addresses. It never searches by a partial name
or subject and never includes unrelated or personal mail.

## Version 8.15 couple payment reference

Native Weddings By Mark quotes and invoices now show one bold, recognisable
bank-transfer reference made from both first names and the wedding date, for
example `BETHSTUART150527`. The same reference is used throughout the quote,
client account, invoice PDF and applicable payment emails. Invoice numbering
and imported Studio Ninja records remain unchanged.

## Version 8.14 complete backup

A large, administrator-only backup button in Business settings downloads a
dated ZIP containing every database record, uploaded document, readable
booking/invoice/payment registers, invoice PDFs, receipts and signed agreement
PDFs, with a manifest and checksums. It changes no booking or workflow and
excludes passwords and integration credentials.

## Version 8.13 live website availability

The public endpoint `/api/public/availability?date=YYYY-MM-DD` answers with only
`Booked`, `Available` or `Unavailable`; it never exposes a couple, venue or other
booking detail. The supplied `WEBSITE-DATE-CHECKER-V8.13.html` preserves the
existing checker design and checks both the existing Studio Ninja/Google Apps
Script diary and BookingSystem2026. A date is advertised as available only when
both sources confirm that it is free.

## Version 8.12 Google Calendar

Native accepted or confirmed weddings sync to the connected account's primary
Google Calendar. The all-day event visibly contains the couple names, first/main
venue and ceremony time. Booking and Wedding Booking Form changes update the same
event; cancellation removes the event but retains the complete cancelled booking.
Google failures remain retryable and never roll back BookingSystem2026 data.

See `RELEASE-NOTES-V8.14.md` and `DEPLOY-V8.14-TRUENAS.txt` for the protected
upgrade instructions. The original Google setup remains in
`DEPLOY-V8.12-TRUENAS.txt`.

## Included in Phase 2A

- Secure single-administrator login with an HTTP-only session cookie
- Responsive Teal Operations interface for desktop, tablet and mobile
- Separate Weddings By Mark and Ivory Digital business profiles
- Wedding booking and digital project records
- Contact information, dates, venue/project, packages, values and notes
- Automatic starter workflow tasks for each new record
- Task completion and dashboard workflow health
- Bank-transfer invoice records with separate counters for each business
- Brand-aware invoice numbers: WBM and Ivory Digital each have their own `02001`, `02002` sequence
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

Version 8.5 includes the protected Studio Ninja import foundation. Imported
records retain their original references, payments, schedules, forms, contract
provenance and documents. Imported weddings remain fully visible in confirmed
totals, upcoming dates, the calendar and workflows. Their automatic emails,
payment confirmations and scheduled reminders remain permanently paused so
Studio Ninja and BookingSystem2026 cannot contact the same couple. Mark can
create a one-off portal link or send one manually confirmed email without
enabling any later automation. New website enquiries retain the normal
BookingSystem2026 email and reminder journey. Gallery automation remains
planned for a later phase without restructuring the core data.

## Version 8 client experience

- Weddings By Mark uses a black, ivory and gold client theme; Ivory Digital uses its own gold and ivory identity
- Real logos replace the temporary initials in the admin sign-in and secure client area
- Couples see a wedding countdown, clear next action, completion ticks and a guided booking journey
- The long Wedding Booking Form is split into three mobile-friendly steps
- Invoice cards, empty states and responsive navigation have been redesigned
- The enquiry form and admin booking editor use Google Places venue autocomplete when configured
- Venue name, full address, Google Place ID and coordinates are saved for one-click directions
- The dashboard highlights enquiries needing attention and shows a notification badge
- Email templates can be previewed with realistic example data and explicitly test-sent

Set `GOOGLE_MAPS_API_KEY` to the website- and API-restricted key created for
`booking.weddingsbymark.uk`. The form remains usable with manual venue entry if the key is absent.

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
