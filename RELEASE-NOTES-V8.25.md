# BookingSystem2026 V8.25 — Personal Quote Email Review

Build: `2026.08.22-quote-email-review-v8.25`

## The safer quote workflow

1. **Prepare quote** opens the existing required extras and private-discount
   controls.
2. **Save quote & review email** saves those quote details and sends nothing.
3. The system loads the existing master **Quote email** template into a temporary
   subject-and-message editor for that particular couple.
4. Mark can add an answer, explanation or personal note and then deliberately
   press **Send quote now**.

The temporary wording is sent and recorded in that couple's email history, but
the saved master Quote email template is never changed.

## Clear states

- A saved unsent quote displays **Quote ready — not sent**.
- **Edit quote** returns to extras and discounts.
- **Review email & send** returns to the temporary email editor.
- A successful send displays **Quote sent — waiting for their choice**.
- Quote-link access tracking and the existing one-day/nine-day follow-ups begin
  only after the quote email has genuinely been sent.

## Safety retained

- The tracked quote link is still generated and inserted at send time.
- Testing Mode redirection remains visible in the review window.
- Studio Ninja imported records remain automation-suppressed.
- Invoice creation remains unchanged and happens only when the couple accepts a
  package.
- No YAML, environment-variable or database migration change is required.
- Every V8.24 dashboard, combined 30-day email, V8.23.2 mobile form and V8.23.1
  complete-backup improvement is retained.
