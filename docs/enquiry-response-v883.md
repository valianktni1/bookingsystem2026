# V8.83: responsive enquiry submission and mobile confirmation

The public request previously waited for two SMTP deliveries after saving the enquiry. The response now follows a database commit containing the enquiry, portal, tasks, audit and exact rendered acknowledgement/owner-notification jobs. No SMTP calls occur in the HTTP handler. A separate two-second worker scans only these persisted new website enquiry jobs; a conditional queued-to-sending update claims each email before sending. Restarted queued jobs survive. Interrupted sending is covered by the existing startup communication failure handling. Uncertain SMTP failures are not automatically resent; existing admin communication retry retains the wording. No historical mail is added to the queue, and protected imports cannot be sent by it.

A small additive enquiry_email_jobs table retains the email-log association, tracking-pixel URL and owner reply-to. Existing recipients, template rendering, tracking/link hashes, test-client recipient protection and manual retry behavior are preserved. Gallery/planner automation and mappings are unchanged.

The confirmation uses normal document flow in standalone and embedded views, a shrinkable single-column grid and explicit word wrapping. Embed completion messages measure the rendered height rather than assuming 520px. Success appears only after the enquiry response; errors retain answers. Versioned assets refresh the enquiry CSS and JavaScript.

Validation: seven isolated request/worker tests verify persisted enquiry+jobs before SMTP, duplicate submission handling, durable worker replay, manual failure handling, tracking/reply-to, unchanged queued wording, protected imports and test-mode client recipient. Production-page browser checks cover standalone/embedded 320, 390, 430, 844 and 1280px, long confirmation text, error retention and post-response success. Existing 17 gallery integration tests pass. No live enquiries or email sends used.

Deployment retains the V8.82 verified database dump, rollback images, exact source pin, preflight and app-only restart. The previously cancelled dropdown length-limit change is omitted; its limit remains 30.
