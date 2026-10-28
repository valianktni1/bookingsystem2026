# V8.82: actionable gallery setup and safe resuming

The old missing-configuration error did not identify its blocking item. The
settings panel showed only today's catalogue, even though accepted invoices
can retain old package/extra identifiers. Repeated Retry also used previously
saved settings and left Needs attention visible above Retry scheduled.

This update:

- Lists exact missing package/extra names per booking and exposes missing rule
  keys in the admin-only response. GET diagnostics remain read-only.
- Adds saved invoice items absent from the current catalogue to the review
  list, labelled saved invoice item. They are never silently assigned features.
- Uses the original package ID when present. Missing IDs get a saved-code key
  or booking-specific identity. Manual/custom items use booking-specific keys,
  so unrelated manual_amendment_0 items cannot share an entitlement rule.
- Preserves existing catalogue rule identities, choices and encrypted key.
- Highlights and lists blocking items first. Save setup & resume waiting
  bookings stores the choices and requeues only validated needs_attention jobs
  with no durable payload/result, proving no gallery create request was sent.
- Leaves attempted requests, lost responses and existing galleries untouched.
  Those still need explicit safe retry/review using the immutable payload.
- Prevents retry/refresh from bypassing unsaved form edits. A deliberate retry
  immediately changes the status text to Retry scheduled and removes the stale
  error. Refresh progress reloads server state only when no edits would be lost.

No migrations, planner changes, gallery-app changes, key reset or bulk data
edits. The 2 December 2026 cutoff, full booking fee, protected import/test
exclusions, upload-link naming and three-day expiry remain unchanged.

Validation: 17 API/worker tests, including old invoice items, named missing
rules, read-only diagnostics, safe resuming, key/choice retention, manual-item
identity isolation and no automatic retry after a lost response. Existing
native/imported booking workspace tests and new settings tests pass across
320/390/768/1280px in both themes with intercepted requests. App imports,
deployment preflight and backup/build/preflight failure guards are checked.

Deploy booking V8.82 only, refresh, open Settings > Wedding galleries. Existing
saved selections remain. Review only items that still need setup, including
any labelled saved invoice item, then Save setup & resume waiting bookings.
Refresh progress after the worker's next scan. No gallery or planner update.
