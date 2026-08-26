# BookingSystem2026 V8.29 - Durable Client Form Drafts

Build: `2026.08.25-durable-form-drafts-v8.29`

## Improved

- The Wedding Booking Form now saves the couple's answers privately on their current device while they type.
- The Final Wedding Timings Form now keeps its draft after a page refresh, browser closure or phone restart.
- Reopening the same secure booking link on the same device restores the saved answers and the exact form step.
- Both forms clearly show when a draft is protected and when saved answers have been restored.
- Drafts are retained for up to 30 days and removed immediately after a successful submission.
- If submission fails, the form stays available and explicitly confirms that the answers remain saved.
- Existing Final Wedding Timings drafts held only for the current browser session are migrated automatically to durable device storage.

## Safety retained

- Drafting sends no email and does not update the booking, invoice, package, payment or Calendar.
- A booking changes only after the couple deliberately presses the final submit button and the server confirms success.
- Drafts remain in the couple's current browser; no new third-party service or tracking is involved.
- Studio Ninja imported-booking communication safeguards are unchanged.
- V8.28.4.2 receipt opening, invoice previews, backups and all existing workflow protections are included cumulatively.

## Desktop workflow review

- The supplied Studio Ninja desktop dashboard and job screen were reviewed as workflow references.
- BookingSystem2026 already provides the useful at-a-glance elements through its journey stage, exact next action, section totals, client details, finance status and activity history.
- No duplicate dashboard was added inside each client record because it would repeat existing information and increase visual clutter.
