# Phase 1 decisions

## Business structure

The application is neutral internally: **Mark's Business Studio**.

Every record belongs to one trading brand:

- **Weddings By Mark** (`wbm`, invoice prefix `WBM`)
- **Ivory Digital** (`ivory`, invoice prefix `ID`)

Documents and future outgoing emails can therefore use the correct trading identity without showing both brands unnecessarily.

## Invoice sequence

Phase 1 uses one transaction-protected numeric counter across both brands. It starts at `2000` so the first generated invoice is number `02001`.

Examples:

1. Weddings By Mark invoice: `WBM02001`
2. Ivory Digital invoice: `ID02002`
3. Weddings By Mark invoice: `WBM02003`

The later Studio Ninja importer will preview every assignment before committing it. Existing wedding bookings will be ordered by their earliest deposit-paid date, with explicit handling for missing or identical dates.

## Migration readiness

The booking record already has fields for:

- `legacy_source` and `legacy_id`
- Complete form/questionnaire data
- Workflow state
- Deposit paid date
- Notes
- Linked tasks, invoices and documents

The actual importer is intentionally deferred until a real Studio Ninja export is available, so its column and attachment structure can be matched accurately.

## Gallery integration readiness

Each booking has a stable UUID and workflow state. A later gallery integration can use this to create the couple's gallery, transfer names and wedding dates, choose package-dependent features, schedule expiry, and write delivery status back to the booking.

