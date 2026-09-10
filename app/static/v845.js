/* V8.45 - everyday enquiry, reschedule and client-chasing workflows. */
(() => {
  "use strict";

  const baseOpenDrawerV845 = openDrawer;
  const baseRenderTabV845 = renderTab;

  const enquiryOutcomeOptionsV845 = [
    ["booked_elsewhere", "Booked another photographer"],
    ["no_response", "No response"],
    ["date_unavailable", "Date unavailable"],
    ["budget", "Budget / price"],
    ["plans_changed", "Plans changed"],
    ["other", "Other reason"],
  ];

  function setModalButtonV845(label) {
    const button = $("#dynamic-form footer .primary");
    if (button) button.textContent = label;
  }

  function openCloseEnquiryV845(record) {
    showModal(
      "Close unsuccessful enquiry",
      `<section class="full v845-safety-note"><i>✓</i><span><strong>This closes the enquiry cleanly</strong><small>It leaves invoices, payments and the email history alone. Nothing is emailed to the couple.</small></span></section>
       <label class="full">What happened?<select id="v845-enquiry-outcome" required>${enquiryOutcomeOptionsV845.map(([value, label]) => `<option value="${value}">${esc(label)}</option>`).join("")}</select></label>
       <label class="full">Private detail (optional)<textarea id="v845-enquiry-detail" maxlength="1000" rows="3" placeholder="Anything useful to remember later"></textarea></label>
       <div class="full v845-no-email">🔒 The enquiry moves to Archived, its link is closed, and no client email is sent.</div>`,
      async () => {
        const result = await api(`/api/bookings/${record.id}/close-enquiry`, {
          method: "POST",
          body: JSON.stringify({
            outcome: value("#v845-enquiry-outcome"),
            details: nullable(value("#v845-enquiry-detail")),
          }),
        });
        closeModal();
        closeDrawer();
        await refresh();
        render();
        toast(result.message);
      },
      "Use this when the couple has not booked. A genuine booked wedding still uses the protected cancellation flow."
    );
    setModalButtonV845("Close enquiry");
  }

  async function reopenEnquiryV845(record) {
    if (!window.confirm(`Reopen ${record.title}'s enquiry?\n\nIts former status and private tasks will be restored. No email will be sent.`)) return;
    try {
      const result = await api(`/api/bookings/${record.id}/reopen-enquiry`, {method: "POST"});
      await refresh();
      toast(result.message);
      await openDrawer(record.id, "Overview");
    } catch (error) {
      toast(error.message, "error");
    }
  }

  function conflictSummaryV845(check) {
    const rows = [];
    (check.conflicts?.blocked_dates || []).forEach(block => rows.push(`Blocked: ${block.label}`));
    (check.conflicts?.records || []).forEach(record => rows.push(`${statusText(record.status)}: ${record.title}`));
    return rows;
  }

  function openRescheduleV845(record) {
    showModal(
      "Move wedding date",
      `<section class="full v845-safety-note"><i>↻</i><span><strong>${esc(fmtEventDate(record.event_date))} → choose the new date</strong><small>The same booking, invoice numbers, payments, files and signed agreement are retained.</small></span></section>
       <label>Current wedding date<input value="${attr(record.event_date || "")}" disabled></label>
       <label>New wedding date<input id="v845-new-date" type="date" min="${new Date().toISOString().slice(0, 10)}" required></label>
       <label class="full">Private reason for the move<textarea id="v845-reschedule-reason" minlength="3" maxlength="1000" rows="3" required placeholder="For example: Couple postponed the wedding"></textarea></label>
       <section id="v845-reschedule-check" class="full v845-date-check"><span>Choose the new date to check availability.</span></section>
       <div class="full v845-no-email">🔒 No email is sent. Google Calendar and future reminder dates are updated after you confirm.</div>`,
      async () => {
        const newDate = value("#v845-new-date");
        const check = await api(`/api/bookings/${record.id}/reschedule-check?new_date=${encodeURIComponent(newDate)}`);
        const conflicts = conflictSummaryV845(check);
        let confirmConflicts = false;
        if (conflicts.length) {
          confirmConflicts = window.confirm(`The new date has ${conflicts.length} clash${conflicts.length === 1 ? "" : "es"}:\n\n${conflicts.join("\n")}\n\nMove this wedding anyway?`);
          if (!confirmConflicts) throw new Error("Wedding date was not changed");
        }
        const result = await api(`/api/bookings/${record.id}/reschedule`, {
          method: "POST",
          body: JSON.stringify({
            new_date: newDate,
            reason: value("#v845-reschedule-reason").trim(),
            confirm_conflicts: confirmConflicts,
          }),
        });
        closeModal();
        await refresh();
        toast(result.message);
        await openDrawer(record.id, "Overview");
      },
      "The old date and reason are retained permanently in Activity. Existing signed paperwork is never rewritten."
    );
    setModalButtonV845("Move wedding safely");
    const input = $("#v845-new-date");
    const result = $("#v845-reschedule-check");
    let sequence = 0;
    input.onchange = async () => {
      const current = ++sequence;
      if (!input.value) return;
      result.className = "full v845-date-check loading";
      result.innerHTML = "Checking the date…";
      try {
        const check = await api(`/api/bookings/${record.id}/reschedule-check?new_date=${encodeURIComponent(input.value)}`);
        if (current !== sequence) return;
        const conflicts = conflictSummaryV845(check);
        result.className = `full v845-date-check ${conflicts.length ? "warning" : "clear"}`;
        result.innerHTML = conflicts.length
          ? `<strong>! ${conflicts.length} clash${conflicts.length === 1 ? "" : "es"} to review</strong><span>${conflicts.map(esc).join(" · ")}</span>`
          : `<strong>✓ No other booking or blocked date found</strong><span>The date will be checked once more when you save.</span>`;
      } catch (error) {
        if (current !== sequence) return;
        result.className = "full v845-date-check warning";
        result.innerHTML = `<strong>Date check unavailable</strong><span>${esc(error.message)}</span>`;
      }
    };
  }

  async function openChaserV845(record, templateKey, title, actionLabel) {
    try {
      const centre = await api(`/api/bookings/${record.id}/email-centre`);
      const template = (centre.templates || []).find(item => item.template_key === templateKey);
      if (!template) throw new Error(`${title} template is not active in Email templates`);
      showModal(
        title,
        `<section class="full v845-recipient"><small>TO</small><strong>${esc(centre.recipient)}</strong><span>Nothing is sent until you press ${esc(actionLabel)}.</span></section>
         <label class="full">Subject<input id="v845-chaser-subject" maxlength="240" value="${attr(template.subject)}" required></label>
         <label class="full">Message<textarea id="v845-chaser-body" maxlength="20000" rows="14" required>${esc(template.body)}</textarea><small class="field-help">You can personalise this one email. The saved master template will not change.</small></label>
         <div class="full v845-link-note">↗ Their secure wedding booking link is added automatically.</div>`,
        async () => {
          await api(`/api/bookings/${record.id}/email-centre/send`, {
            method: "POST",
            body: JSON.stringify({
              mode: "template",
              template_key: templateKey,
              subject: value("#v845-chaser-subject").trim(),
              body: value("#v845-chaser-body").trim(),
            }),
          });
          closeModal();
          state.currentPortal = await api(`/api/bookings/${record.id}/portal`);
          toast(`${title} sent`);
          await openDrawer(record.id, "Journey");
        },
        "This is a deliberate one-off reminder, not a new automatic workflow."
      );
      setModalButtonV845(actionLabel);
    } catch (error) {
      toast(error.message, "error");
    }
  }

  function enhanceJourneyV845(record, body) {
    if (!body || body.querySelector(".v845-chaser-panel")) return;
    const portal = state.currentPortal || {};
    if (
      record.kind !== "wedding"
      || record.legacy_source
      || record.status === "cancelled"
      || record.automation_suppressed
      || !portal.quote
    ) return;
    const bookingForm = (portal.submissions || []).find(item => item.form_type === "booking_form");
    const contract = portal.contract;
    let key = null;
    let heading = "";
    let detail = "";
    let button = "";
    if (!bookingForm) {
      key = "booking_form_reminder";
      heading = "Waiting for their Wedding Booking Form";
      detail = "Review a friendly reminder and send it only when you decide it is needed.";
      button = "Review & send form reminder";
    } else if (!contract) {
      key = "contract_reminder";
      heading = "Waiting for their wedding agreement";
      detail = "The form is safely received. You can now send a separate agreement reminder.";
      button = "Review & send agreement reminder";
    }
    if (!key) return;
    const panel = document.createElement("section");
    panel.className = "v845-chaser-panel";
    panel.innerHTML = `<i>✉</i><div><small>CLIENT FOLLOW-UP · MANUAL</small><strong>${esc(heading)}</strong><span>${esc(detail)}</span></div><button type="button" class="secondary">${esc(button)}</button>`;
    panel.querySelector("button").onclick = () => openChaserV845(record, key, heading, "Send reminder");
    body.prepend(panel);
  }

  function enhanceReplyStatusV845(record, body) {
    if (!body || body.querySelector(".v845-reply-detected")) return;
    const reply = state.currentPortal?.quote_reply_detection;
    const controls = body.querySelector(".v843-followups");
    if (!reply || !controls) return;
    controls.insertAdjacentHTML("beforebegin", `<section class="v845-reply-detected"><i>↩</i><div><small>COUPLE REPLIED AFTER THE QUOTE</small><strong>The next-day check was paused automatically</strong><span>Reply detected ${esc(fmtDateTime(reply.first_reply_at))}. Your final nine-day check remains independent and can still be paused or left active below.</span></div></section>`);
  }

  function enhanceRecordActionsV845(record) {
    const drawer = $("#drawer");
    const primary = $(".record-primary-actions", drawer);
    if (!primary) return;
    const closure = record.workflow_state?.enquiry_closure;
    const hasFinancialProgress = (record.invoices || []).some(invoice => Number(invoice.paid || 0) > 0 || invoice.accepted_quote_invoice);
    const openEnquiry = record.brand === "wbm" && record.kind === "wedding"
      && ["enquiry", "quoted"].includes(record.status) && !hasFinancialProgress;
    if (closure) {
      primary.innerHTML = `<button type="button" class="secondary v845-reopen-enquiry">↶ Reopen enquiry</button>`;
      primary.querySelector(".v845-reopen-enquiry").onclick = () => reopenEnquiryV845(record);
      const archive = $("#archive-record", drawer);
      if (archive) {
        archive.disabled = true;
        archive.textContent = "Use Reopen enquiry above";
      }
      return;
    }
    if (openEnquiry) {
      primary.innerHTML = `<button type="button" class="secondary v845-close-enquiry">Close enquiry</button>`;
      primary.querySelector(".v845-close-enquiry").onclick = () => openCloseEnquiryV845(record);
      return;
    }
    if (
      record.brand === "wbm"
      && record.kind === "wedding"
      && ["confirmed", "in_progress"].includes(record.status)
      && !primary.querySelector(".v845-reschedule")
    ) {
      primary.insertAdjacentHTML("afterbegin", `<button type="button" class="secondary v845-reschedule">↻ Move wedding date</button>`);
      primary.querySelector(".v845-reschedule").onclick = () => openRescheduleV845(record);
    }
  }

  renderTab = async function (record, tab, target = null) {
    await baseRenderTabV845(record, tab, target);
    const body = target || $("#drawer-body");
    const selected = normaliseRecordTab(tab);
    if (selected === "Journey") enhanceJourneyV845(record, body);
    if (selected === "Emails") enhanceReplyStatusV845(record, body);
  };

  openDrawer = async function (id, tab = "Overview") {
    await baseOpenDrawerV845(id, tab);
    if (state.current?.id === id) enhanceRecordActionsV845(state.current);
  };

  window.WBMWorkflowsV845 = Object.freeze({
    version: "8.45",
    actions: ["close-enquiry", "reopen-enquiry", "reschedule", "manual-form-chaser", "manual-agreement-chaser"],
  });
})();
