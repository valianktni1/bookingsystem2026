# BookingSystem2026 V8.33.2 — Streaming Complete Backup

Build: `2026.08.31-streaming-complete-backup-v8.33.2`

## Backup repair

- Large live backups no longer sit silently at 32% while all invoice, receipt and signed-agreement PDFs are generated.
- Progress now advances through **PDF X of Y**, showing which invoice, receipt or agreement is being processed.
- Each completed PDF is written directly into the ZIP instead of keeping the entire PDF batch in application memory.
- Broken historic records remain non-blocking and are listed as warnings in the manifest.
- The final ZIP still includes the complete typed database snapshot, readable registers, generated PDFs, uploaded files, running source and checksums.

## Included

V8.33.2 also contains the V8.33.1 **Download PDF** button inside the completed Final Wedding Timings pop-up.
