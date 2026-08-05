# BookingSystem2026 V8.4

This is the complete cumulative build based on V8.3. It prepares the application for the Studio Ninja migration without importing any live records.

## Migration safety

- Imports require the exact phrase `IMPORT WITHOUT EMAILS`.
- Every imported booking starts with client email and reminder automation paused.
- No portal link is created or emailed by the import endpoint.
- Activation is per booking and requires `ACTIVATE CLIENT EMAILS`.
- Duplicate Studio Ninja job IDs are rejected.
- Original imported payments and source documents cannot be deleted through the interface.

## Retained history

- Current WBM invoice number and previous Studio Ninja invoice/quote references.
- Each bank-transfer payment and the original instalment schedule.
- Questionnaire answers and their original completion date.
- Contract acceptance date with its evidence source. No historic IP address is fabricated.
- Original client-visible PDFs in a dedicated Documents section.
- A Studio Ninja timeline on the admin record.

## Client experience

- Imported forms show as completed and remain editable by the couple.
- The original invoice reference and instalment schedule are shown clearly.
- Final wedding details open automatically 30 days before the wedding, with a manual early-open control for Mark.

The Studio Ninja records and files are intentionally not included in this application ZIP. They will be imported only after this version is deployed, backed up and checked.
