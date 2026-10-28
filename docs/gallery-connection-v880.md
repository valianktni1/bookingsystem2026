# Personal WBM booking → gallery connection (booking 8.81 / gallery 2.4)

Deploy gallery first, booking second. The connection is off by default. V8.81 includes existing native bookings for
weddings from 2 December 2026 onwards. No client email is sent by this integration.

## Set up

1. Gallery Settings → Booking connection: create a key, copy it, then Enable.
   Rotation pauses the connection. The key is shown once and stored hashed.
2. Booking Settings → Wedding galleries: paste the key. For each package, mark
   Reviewed and select Wedding Images, Video, Full-day and/or SelfieBooth plus
   Off / 40 + cover / 60 + cover for its album. Configure selected extras and
   adjustments as well: free albums sometimes live in £0 adjustment entries.
   Travel and ordinary discounts can be Reviewed with every gallery option off.
   A 60-photo album upgrade takes precedence over an included 40-photo album.
3. Enable gallery creation and save. Wedding dates must be strictly after
   1 December 2026 (2 December onwards), regardless of when the quote was
   accepted or the connection enabled. The full booking fee must be recorded against their
   accepted quote's open invoice. Partial fees, protected imports, test records,
   Ivory projects, cancelled/archived bookings and weddings on/before 1 December
   2026 are out. Existing matching galleries are flagged, never duplicated.
4. For a qualifying booking the worker runs every 30 seconds. It saves both the
   durable request and result. Overview shows the gallery link; Settings shows
   retry/review state. Missing mappings are visible and do not guess from names.

## What is created

- `John & Nikki 20.12.26` and the lead email only, plus folder/album settings.
- Wedding Images / Video / SelfieBooth according to the reviewed package/extra.
- Album Favourites and the actual album controls if an album is included/paid.
- Guest Uploads only for full-day, plus an upload-only guest share. Address is
  `https://weddingsbymark.uk/s/johnnikkiguestuploads`, then suffix 2, 3… if taken.
- Guest link expiry matches the existing gallery rule: **00:01 UTC on the third
  day after the wedding**. This is unchanged; it is not three days after creation.
- No main gallery share, ready notification, QR-choice email or publication.
  Send the existing QR-design choice email yourself nearer the wedding.

Gallery keys cannot sign in as admin or edit an existing gallery. Requests use
fixed HTTPS origins, verified TLS and no redirects. Booking stores its key
encrypted with the session secret; retain the existing .env in backups.

## Retries and manual control

The booking ID, deterministic gallery/share IDs, immutable request and unique
share-token index prevent duplicates on retry. An existing same-name folder is
flagged rather than adopted, renamed or merged. Reservations survive restarts.
Concurrent claims are leased. Partial creation is resumed, not recreated.
Neither old galleries nor links are auto-linked by email/name alone.

Created galleries remain editable with existing controls. Later date, name,
email, package, invoice-item or entitlement-rule changes flag Needs review;
no gallery change or deletion is requested. After adjusting/checking the gallery,
click I have checked and adjusted this gallery in booking Settings to acknowledge.
Removed galleries/shares are not recreated by a completed request. A changed
request after a network attempt is stopped for review, including lost responses.
Review checks do not remove photos, favourites, album choices or manual edits.

Retries call the original immutable create request; they never replace the
payload after a possibly successful network request. An interrupted job whose
booking has changed needs manual investigation. Pausing either connection is
safe: booking keeps its durable retry state. The wedding-date cutoff applies
also to retries, so moving an uncreated booking to 1 December or earlier cannot
create its gallery. Existing linked galleries are never removed.

## Validation and deployment

Tests use disposable SQLite and mock Mongo, temporary folders and intercepted
browser APIs. Cover authentication/rotation/pause, album/free/paid mappings,
deposit/date-cutoff/import rules, link collisions, expiry and guest scope,
interrupted replay, immutable payloads, manual changes, review acknowledgement
and both themes/mobile layouts. Real worker → real HTTP intake contract passes
against temporary stores with exactly one gallery/share and no email records.
Existing planner (13 tests), booking workspace, gallery album/share/path tests
and a full production frontend build are also checked. The frontend retains
two pre-existing hook warnings in AdminActivity and ShareView; no new warnings.

Deployment scripts back up each database before building pinned commits, retain
running images, preflight imports/assets and print rollback commands. They do
not rewrite the live compose or .env, chmod data, or restart databases. The
gallery script is mirrored as DEPLOY-GALLERY-V2.4.sh in the public booking repo,
so it can be downloaded even while the gallery repo is private. A private image
build prompts for a GitHub read token passed as a BuildKit secret, never printed.
No planner deployment is required. Actual TrueNAS deploy is user-run.
