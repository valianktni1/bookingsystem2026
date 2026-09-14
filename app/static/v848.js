/* V8.48 - audited exceptional payment arrangements. */
(() => {
  const baseRenderFinanceV848 = renderFinance;

  function calendarLabelV848(record) {
    const calendar = record.workflow_state?.google_calendar || {};
    if (calendar.status === "synced") return "✓ Google Calendar synced";
    if (calendar.status === "error") return "Google Calendar retry pending";
    return "Google Calendar sync queued";
  }

  function arrangementEligibleV848(record) {
    return record.brand === "wbm"
      && record.kind === "wedding"
      && !record.legacy_source
      && !record.is_test
      && !["cancelled", "completed"].includes(record.status)
      && Boolean(record.event_date)
      && (record.invoices || []).some(invoice =>
        invoice.accepted_quote_invoice
        && !["paid", "void", "cancelled"].includes(invoice.status)
        && Number(invoice.paid || 0) <= 0
      );
  }

  function arrangementPanelV848(record) {
    const arrangement = record.payment_arrangement;
    const active = Boolean(arrangement?.active);
    if (!active && !arrangementEligibleV848(record)) return null;
    const panel = document.createElement("section");
    panel.className = `v848-payment-arrangement ${active ? "active" : "available"}`;
    if (active) {
      panel.innerHTML = `<header><i>✓</i><div><small>SPECIAL PAYMENT ARRANGEMENT</small><h3>Date secured — no payment recorded</h3><p>This wedding is protected in the date checker and Google Calendar without creating a false deposit.</p></div><b>SECURED</b></header><dl><dt>Agreed payment date</dt><dd>${esc(fmtEventDate(arrangement.agreed_payment_date))}</dd><dt>Payment reminders</dt><dd>${arrangement.pause_payment_reminders ? "Paused for this arrangement" : "Active around the agreed date"}</dd><dt>Google Calendar</dt><dd>${esc(calendarLabelV848(record))}</dd><dt>Private reason</dt><dd>${esc(arrangement.reason || "Recorded special arrangement")}</dd></dl><footer><span>Normal wedding check-ins still run. Recording a genuine payment ends this exception automatically.</span><button type="button" class="secondary" data-v848-remove>Remove arrangement</button></footer>`;
      panel.querySelector("[data-v848-remove]").onclick = () => removeArrangementV848(record);
    } else {
      panel.innerHTML = `<header><i>!</i><div><small>EXCEPTIONAL BOOKINGS ONLY</small><h3>Need to secure this date before payment?</h3><p>Use this only when you have personally agreed that this couple can pay later.</p></div></header><footer><span>No payment will be created and nothing will be emailed automatically.</span><button type="button" class="secondary" data-v848-secure>Secure by special agreement</button></footer>`;
      panel.querySelector("[data-v848-secure]").onclick = () => secureArrangementV848(record);
    }
    return panel;
  }

  function secureArrangementV848(record) {
    showModal(
      "Secure date without payment",
      `<div class="v848-modal-warning full"><strong>No payment will be recorded</strong><span>This deliberately confirms the wedding, protects the public date checker and adds it to Google Calendar.</span></div><label class="full">Agreed payment date<input id="v848-payment-date" type="date" value="${attr(record.event_date || "")}" max="${attr(record.event_date || "")}" required></label><label class="full">Private reason<textarea id="v848-reason" rows="4" required minlength="10" placeholder="For example: Full payment agreed on the wedding day following the couple's recent scam experience"></textarea></label><label class="v848-check full"><input id="v848-pause-reminders" type="checkbox" checked><span><strong>Pause automatic payment reminders</strong><small>The 120-day and 30-day wedding check-ins will continue normally.</small></span></label><label class="full">Type <strong>SECURE WITHOUT PAYMENT</strong><input id="v848-confirm" autocomplete="off" required></label>`,
      async () => {
        const result = await api(`/api/bookings/${record.id}/payment-arrangement`, {
          method: "POST",
          body: JSON.stringify({
            agreed_payment_date: value("#v848-payment-date"),
            reason: value("#v848-reason").trim(),
            pause_payment_reminders: $("#v848-pause-reminders").checked,
            confirmation: value("#v848-confirm").trim(),
          }),
        });
        closeModal();
        await refresh();
        toast(result.message);
        openDrawer(record.id, "Payments");
      },
      "The invoice payment dates will show the date you agreed. This sends no email and records no money."
    );
    $("#dynamic-form button[type='submit']").textContent = "Secure date";
  }

  function removeArrangementV848(record) {
    showModal(
      "Remove special payment arrangement",
      `<div class="v848-modal-warning danger full"><strong>The wedding date will become provisional again</strong><span>Its automatic Google Calendar booking will be removed unless a genuine payment exists.</span></div><label class="full">Private reason<textarea id="v848-remove-reason" rows="3" required minlength="5" placeholder="Why is this arrangement being removed?"></textarea></label><label class="full">Type <strong>REMOVE PAYMENT ARRANGEMENT</strong><input id="v848-remove-confirm" autocomplete="off" required></label>`,
      async () => {
        const result = await api(`/api/bookings/${record.id}/payment-arrangement`, {
          method: "DELETE",
          body: JSON.stringify({
            reason: value("#v848-remove-reason").trim(),
            confirmation: value("#v848-remove-confirm").trim(),
          }),
        });
        closeModal();
        await refresh();
        toast(result.message);
        openDrawer(record.id, "Payments");
      },
      "Any invoice fields changed after the arrangement was made are preserved rather than overwritten."
    );
    $("#dynamic-form button[type='submit']").textContent = "Remove arrangement";
  }

  renderFinance = function (record, body) {
    baseRenderFinanceV848(record, body);
    const panel = arrangementPanelV848(record);
    if (panel) body.prepend(panel);
  };

  window.WBMPaymentArrangementsV848 = Object.freeze({version: "8.48"});
})();
