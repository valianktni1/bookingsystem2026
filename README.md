## V8.61: direct paperwork review

Direct dashboard Review destinations, readable saved quote details, original enquiry access and compact native quote panels. Desktop/mobile browser checks completed. See DEPLOY-V8.61-READ-ME.txt.

## V8.60: remember your place

Restores admin booking/list scroll after reload and remembers the section in the same browser tab. See DEPLOY-V8.60-READ-ME.txt. Includes V8.59.

## V8.59: clearer native invoice PDFs

Embedded fonts, compact layout and payment schedule status from recorded payments. Existing invoice values, labels and protected import rendering preserved. See DEPLOY-V8.59-READ-ME.txt.

## V8.58: quote review, preview and bank labels

See DEPLOY-V8.58-READ-ME.txt. Includes all previous V8.57.1 changes.

## V8.57.1: email logo contrast

Includes V8.57 in full. Use DEPLOY-V8.57.1-READ-ME.txt.
WBM email logo images include a solid cream backing for dark email headers.

## V8.57: reusable quote templates and two bank accounts

See DEPLOY-V8.57-READ-ME.txt for deployment and how to use the new controls.

## Current release: V8.56.1

Restores the direct Final timings shortcut for native and protected imported bookings.
Deploy instructions: **DEPLOY-V8.56.1-READ-ME.txt**.

## Current release: V8.56

Start with **DEPLOY-V8.56-READ-ME.txt**. Docker builds directly from GitHub;
TrueNAS needs only the deployment helper, not git pull or a source archive.

## Current release: V8.55

Read **DEPLOY-V8.55-READ-ME.txt** for the correct TrueNAS download/update commands.
This server folder is not a Git checkout: do not run git pull there.
Read **VALIDATION-V8.55.txt** for checks.

## Current release: V8.54

Personal wedding booking app: clearer invoice descriptions, simpler dashboard and booking navigation.
Start with **DEPLOY-V8.54-READ-ME.txt** for GitHub Desktop and TrueNAS instructions.
See **VALIDATION-V8.54.txt** for checks and limitations.

# Mark's Business Studio — Version 8.52

Mark's private, self-hosted booking and business management system. The current
build includes every cumulative feature through V8.52, including browser-history
navigation, the client Email Centre, safe one-way Google Calendar syncing and a
privacy-safe live website availability check.

## Version 8.52 Custom Workflow Builder

The Workflow Studio can now create complete extra client journeys without code.
Each new workflow starts as a safe draft, chooses a trigger, before/after timing,
Automatic/Review first/Task only action and an existing or newly-created email
template. Drafts can be previewed and test-emailed before activation, then paused,
edited, duplicated or safely deleted.

Activation defaults to bookings created from that point forward. Including
current eligible bookings is a separate, strongly warned choice, preventing an
old client list from unexpectedly receiving a newly invented workflow. Existing
V8.51 built-in workflows, timings, approvals and protections remain unchanged.

## Version 8.51 Custom Workflow Studio

Weddings By Mark now has a visual Workflow Studio above Email & SMS templates.
Every client-email journey has its own number of days and one of four deliberate
modes: **Automatic**, **Review first**, **Task only**, or **Off**. Review-first
messages wait in a private approval queue with the real couple-specific branded
email preview; Task-only workflows create a Things to do item and send nothing.

The live V8.50.2 timings are the V8.51 defaults, so deployment alone changes no
schedule and sends no email. Existing per-couple quote pauses, reply detection,
payment-arrangement pauses, imported Studio Ninja protections and inactive-email
template safeguards all remain in force. Settings are stored in the existing
system settings table, requiring no database migration.

## Version 8.50.2 workflow cleanup

The inaccurate **Final-detail calls** block has been removed from Home. Upcoming
Weddings remains Mark's practical list, while each booking keeps its private final
telephone-call task dated for the Monday immediately before the wedding.

**Mark wedding complete** is now one deliberate confirmation. Delivery notes,
album progress and an outstanding balance remain visible but never prevent Mark
from completing the wedding. Completion moves it out of Upcoming Weddings and
keeps the complete record under All bookings. Nothing is deleted, no invoice or
payment history is changed, no client email is sent, and the wedding can still be
reopened.

## Version 8.50.1 Inbox flow correction

The live Inbox now has its own clearly labelled search. The main client and
invoice search can no longer carry across silently and hide otherwise visible
emails while the mailbox unread counter continues to show them. Opening Inbox
normally always shows the complete mailbox; opening it from a couple deliberately
filters to that address and displays an obvious **Show all emails** action.

This release changes no mailbox contents, bookings, reminders, invoices,
payments or database records and sends no email during deployment.

## Version 8.50 stability and UK-time safety

The approved organised awards panel—including County Brides Winner 2026 and
Nominated 2027—is used centrally by Weddings By Mark emails, mailbox replies,
previews and PDFs. Its email-safe PNG remains sharp while avoiding a 1.7 MB
attachment on every message.

Automatic client emails and optional automatic SMS are now permitted only from
09:00 until 19:00 Europe/London. British Summer Time is handled automatically;
manual emails and texts remain available whenever Mark deliberately chooses to
send one. Automatic SMS and all seven automatic SMS templates remain disabled
by default.

Quote follow-up dates are calculated from the UK date of the original email,
rather than the UTC date stored in the database. The production configuration
also rejects the old example administrator password, and the fresh-install
recovery catalogue now contains the current Platinum (£1,350) and Ultimate
(£1,799) prices. Existing live package records are never overwritten.

## Version 8.49 SMS centre

Each booking now has a clear **Texts** tab and a direct **Text** shortcut on
desktop and mobile. It sends through The SMS Works, retains the exact wording,
provider message reference and delivery state, and can attach incoming replies
to the correct booking when an SMS Works virtual reply number is configured.

SMS is deliberately disabled by default. The API token remains in the private
TrueNAS environment and is never stored in the database, returned to the
browser or included in the complete in-app backup. TEST bookings can only text
the separate `SMS_TEST_NUMBER`; they cannot text the saved client number.

Seven optional automatic SMS templates mirror the useful points in the email
journey. Every template starts inactive, the global automatic-SMS switch starts
off, and every couple has a separate pause switch for every text. Existing email
reminders are independent and unchanged. Studio Ninja imports remain automatic-
SMS protected but can be texted manually after Mark reviews the exact message.

## Version 8.48.1 friendly invoice filename hotfix

Invoices and receipts opened or downloaded from the secure preview now retain a
recognisable filename containing the couple, wedding date and WBM invoice number.
For example: `Marnie-and-Robert-30-October-2026-WBM02519-Invoice.pdf`.

The secure in-app preview remains unchanged. The hotfix prevents Samsung and
other mobile PDF viewers from substituting a temporary UUID when **Open PDF** is
used. It changes no PDF content, invoice numbers, payments, emails, Accounts
records, reminders or Google Calendar events.

## Version 8.48 exceptional payment arrangements

V8.48 adds a deliberate, administrator-only way to secure one genuine wedding
when Mark has agreed in writing that payment can be made later. It creates no
payment record. Instead it records the agreed date and private reason, updates
the live invoice dates, confirms the booking, protects the public availability
checker and safely creates the normal Google Calendar wedding event.

Payment reminders are paused by default for the arrangement while the ordinary
120-day and 30-day wedding check-ins continue. A real payment completes the
exception automatically. Deleting that payment reactivates the protection, and
removing the arrangement deliberately restores the prior provisional state and
invoice dates without overwriting any later manual changes. All actions are
audited and the feature requires typed confirmation.

## Version 8.47.1 Growth planning bridge

Growth can now securely request genuine Booking totals for a selected wedding
year. The figures include only won Weddings By Mark work and exclude tests,
cancellations, archived records, open enquiries and Ivory Digital jobs. This
restores the Business Plan without guessing zero totals or changing any booking.

## Version 8.47 website revenue attribution

The public enquiry iframe can now receive a consented random website-visit reference
from perfectweddingsbymark.uk. Booking stores it privately with the enquiry and returns
it through the existing authenticated Growth sync. No form answers, email address or
selected wedding date are added to the analytics event. Booking remains the only place
that owns quotes, invoices, contracts, emails and client records. Every V8.46 feature
below remains unchanged.

## Version 8.46 after-wedding workflow

Past Weddings By Mark jobs now have one clear **After the Wedding** panel in
Journey and a compact progress card in Overview. It tracks photograph and video
delivery dates and links, album selection/design/order/delivery, and the account
balance without changing the accepted quote, invoice number, payments, agreement
or client files.

**Mark wedding complete** unlocks only after the wedding date has passed, all
contracted delivery is finished (or marked not required), and the balance is
clear. The optional review request always opens for checking and editing before
Mark deliberately sends it; nothing in this workflow sends automatically.
Studio Ninja imports remain manual-only. The state is retained in the existing
booking workflow record, so V8.46 requires no database migration.

V8.46 also makes two small but useful client-workflow improvements: a quote opens
with no package preselected, while required add-ons remain protected, and every
admin wedding date now includes its full weekday in the dashboard, enquiry and
wedding lists, mobile navigation, couple header and Overview.

## Version 8.45.2 Journey quote-routing hotfix

The combined Journey screen now calls its real Quote and Booking Form renderers
directly. This fixes the later navigation layer that was incorrectly showing
Notes & Activity inside both panels and hiding the V8.45.1 **Edit quote** button.
Fresh cache markers ensure browsers load the corrected scripts immediately.

## Version 8.45.1 sent-quote editing

A quote that has been emailed but is still awaiting the couple's acceptance now
keeps a clear **Edit quote** button in Journey. Required extras and private
discounts can be changed safely; saving updates the couple's existing secure
quote link without sending another email or creating an invoice. Once accepted,
the quote and invoice remain locked exactly as before.

## Version 8.45 everyday workflows

Open enquiries can now be closed with a useful private outcome—such as no
response, booked elsewhere or plans changed—without treating them as cancelled
weddings. The enquiry is archived, its link and automation are safely stopped,
and it can be reopened with its earlier status and tasks restored. No email is
sent and no financial record is changed.

Live booked weddings have a dedicated **Move wedding date** action. It checks
the proposed date for other records and private date blocks, retains the booking,
invoice numbers, payments, files and signed agreement snapshot, and moves the
live invoice dates, private call task and Google Calendar event. The reason and
old date stay in Activity, and moving the date sends no client email.

The Journey now offers clear, deliberate **review and send** reminders when the
Wedding Booking Form or agreement is still outstanding. These are never sent
automatically. A cached, header-only mailbox check also detects a genuine client
reply after a quote and pauses only the next-day quote check; the independent
final nine-day check remains exactly under Mark's control.

## Version 8.44 stable workspace foundation

The individual booking window now has one final navigation controller and the
same six predictable sections everywhere: **Overview, Journey, Emails, Payments,
Files and Activity**. Older internal names and bookmarked routes are translated
safely, while each visible tab is sent directly to the correct existing feature.

On mobile, the previous long accordion is replaced with a compact two-row tab
grid and one clear content area. This release changes presentation and routing
only; reminder timing, emails, invoices, payments, client data and database rules
are unchanged.

## Version 8.43.1 email workspace hotfix

Fixes the booking navigation compatibility fault that could highlight **Emails**
while displaying **Notes & Activity** underneath. The Emails tab now always
renders the email workspace, including both independent quote follow-up controls.
No reminder timing, booking data or email automation is changed.

## Version 8.43 individual quote follow-ups

Each native wedding enquiry now has two separate controls inside **Emails**:
**Next-day follow-up** and **Final nine-day check**. Either email can be paused
or resumed without changing the other. The control sends nothing immediately,
does not affect payment reminders or wedding check-ins, and becomes read-only
after that email has sent or the quote is accepted. Every change is retained in
the private booking activity history. Both standard messages remain editable
and clearly labelled Automatic under Email Templates.

## Version 8.42.1 dashboard hotfix

Removes an obsolete browser helper call that could replace Today with
`setMode is not defined`. A new cache marker ensures browsers fetch the repaired
dashboard script. No booking data, workflow, email or integration behaviour is
changed.

## Version 8.42 fast dashboard and couple emails

The Today dashboard now displays its local booking queues immediately and checks
Hostinger for replies afterward, so a slow external mailbox cannot hold the whole
app on its loading screen. Short-lived mailbox-header caching and per-business
scan locking stop the dashboard, Inbox and Growth synchroniser from opening the
same mailbox scan repeatedly. Each couple now has a direct **Emails** workspace
on desktop and mobile showing sent, opened and secure-link evidence immediately,
with the full private conversation loaded beneath it. Growth communication facts
are loaded in batches; the V8.41 Growth availability contract is unchanged.

## Version 8.36.1 clean current-version label

The header now shows one concise **BOOKINGSYSTEM2026 · COMPLETE V8.36.1** label
instead of an increasingly long list of earlier feature releases. This is a
presentation-only tidy-up and changes no booking-system behaviour.

## Version 8.36 private owner progress notifications

Mark now receives a private branded email when a couple accepts their quote,
submits or updates their Wedding Booking Form/questionnaire, signs their wedding
agreement, or submits or updates their Final Wedding Timings. Each message names
the couple and wedding, links straight to the relevant private booking section,
and uses Reply-To for the couple's address. Recent quote acceptances and completed
agreements are also prominent in the **New client updates** area on Today. A
notification failure never rolls back the couple's action; it is retained in the
existing communication-problems queue for a deliberate retry. Owner messages are
excluded from the client portal and the couple's conversation history.

## Version 8.35 holidays and blocked dates

The Calendar now has a clear **Block dates / holiday** action for one day or
an inclusive date range. Each block is a private availability record: the
public website checker returns only **Booked**, a new enquiry on that date gets
a prominent **DATE BLOCKED** admin warning, and one private all-day Google
Calendar event covers the complete period. Editing a block updates that event;
removing it removes the event and releases the website dates unless a genuine
wedding still protects them. Private labels and notes never reach the public
checker, and no client, quote, invoice or client email is created. Date blocks
and their audit history are included in complete backups.

## Version 8.34 protected accepted-invoice amendments

The accepted BookingSystem invoice can now be amended while it still has an
outstanding balance. Mark can add later-agreed lines—including a zero-price
**Complimentary extra hour**—without replacing or renumbering the invoice. The
accepted quote snapshot, client portal, invoice PDF, booking total and payment
schedule stay aligned; existing payments and an individually agreed final due
date are preserved. Every amendment requires a private reason and is retained
in the audit history. Paid-in-full, cancelled, void and imported invoices remain
locked, and saving an amendment sends no email or Accounts request.

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
