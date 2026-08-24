/* Version 8.2 — safe cancellation, voiding, resets and permanent deletion. */
(function () {
  "use strict";

  const baseOpenDrawerV82 = openDrawer;
  const baseRenderOverviewV82 = renderOverview;
  const baseRenderQuotePortalV82 = renderQuotePortal;
  const baseRenderClientPortalV82 = renderClientPortal;
  const baseOpenRecordModalV82 = openRecordModal;

  function setModalActionLabel(label) {
    const button = $("#dynamic-form footer .primary");
    if (button) button.textContent = label;
  }

  function reasonModal(title, introduction, actionLabel, onSubmit) {
    showModal(
      title,
      `<div class="full v82-modal-warning">${esc(introduction)}</div>
       <label class="full">Reason<textarea id="v82-reason" rows="4" required minlength="3" placeholder="Add a clear reason for the audit history"></textarea></label>`,
      onSubmit,
      "This action is recorded in the booking history."
    );
    setModalActionLabel(actionLabel);
  }

  function confirmedDeleteModal(title, introduction, phrase, onSubmit) {
    showModal(
      title,
      `<div class="full v82-delete-warning"><strong>This cannot be undone</strong><span>${esc(introduction)}</span></div>
       <label class="full">Reason<textarea id="v82-reason" rows="4" required minlength="3" placeholder="Test record, duplicate, spam or other reason"></textarea></label>
       <label class="full">Type <strong>${esc(phrase)}</strong> to confirm<input id="v82-confirmation" autocomplete="off" required placeholder="${attr(phrase)}"></label>`,
      onSubmit,
      "Permanent deletion is intended for tests, duplicates, mistakes and spam—not normal cancellations."
    );
    setModalActionLabel("Permanently delete");
  }

  function localTodayV899() {
    const now = new Date();
    const offset = now.getTimezoneOffset() * 60000;
    return new Date(now.getTime() - offset).toISOString().slice(0, 10);
  }

  async function cancelRecordV82(r) {
    const invoices = (r.invoices || []).filter(invoice => !["void", "cancelled"].includes(invoice.status));
    const unpaid = invoices.reduce((sum, invoice) => sum + Number(invoice.balance || 0), 0);
    const retained = (r.invoices || []).reduce((sum, invoice) => sum + Number(invoice.paid || 0), 0);
    showModal(
      `Cancel ${r.kind === "wedding" ? "booking" : "project"}`,
      `<div class="full v899-cancel-summary"><strong>This closes the booking without deleting its financial history.</strong><dl><dt>Unpaid balance being closed</dt><dd>${money(unpaid)}</dd><dt>Payments currently retained</dt><dd>${money(retained)}</dd><dt>Client email</dt><dd>None will be sent</dd></dl></div>
       <label class="full">Cancellation date<input id="v899-cancellation-date" type="date" value="${localTodayV899()}" max="${localTodayV899()}" required></label>
       <label class="full">Cancellation reason<textarea id="v82-reason" rows="4" required minlength="3" placeholder="For example: couple cancelled their September wedding"></textarea></label>`,
      async () => {
        const result = await api(`/api/bookings/${r.id}/cancel`, {
          method: "POST",
          body: JSON.stringify({
            reason: value("#v82-reason").trim(),
            cancellation_date: value("#v899-cancellation-date")
          })
        });
        closeModal();
        await refresh();
        toast(result.message || "Record cancelled");
        await openDrawer(r.id, "Overview");
      },
      "All invoice numbers, payments, documents and signed records are retained permanently. Open tasks, reminders and portal access stop immediately."
    );
    setModalActionLabel(`Cancel & close ${money(unpaid)}`);
  }

  async function reopenRecordV82(r) {
    reasonModal(
      "Reopen cancelled record",
      "This restores the status held before cancellation and reopens tasks that were outstanding at that time. Previously revoked client links remain revoked for security.",
      "Reopen record",
      async () => {
        const result = await api(`/api/bookings/${r.id}/reopen`, {
          method: "POST",
          body: JSON.stringify({ reason: value("#v82-reason").trim() })
        });
        closeModal();
        await refresh();
        toast(result.message || "Record reopened");
        await openDrawer(r.id, "Overview");
      }
    );
  }

  async function permanentlyDeleteRecordV82(r) {
    const phrase = `DELETE ${r.title}`;
    confirmedDeleteModal(
      "Delete test or duplicate record",
      "The booking/project, zero-payment invoices (including a voided test invoice), tasks, notes, documents, quotes, portal links, submitted forms, agreement acceptance, emails and reminder history will be deleted. Any consumed invoice number stays consumed and is never reused. Records containing genuine payments remain protected.",
      phrase,
      async () => {
        const result = await api(`/api/bookings/${r.id}/permanent-delete`, {
          method: "POST",
          body: JSON.stringify({
            reason: value("#v82-reason").trim(),
            confirmation: value("#v82-confirmation")
          })
        });
        closeModal();
        closeDrawer();
        await refresh();
        render();
        toast(result.message || "Record permanently deleted");
      }
    );
    setModalActionLabel("Delete test / duplicate");
  }

  function enhanceDrawerV82(r) {
    const primary = $(".record-primary-actions", $("#drawer"));
    const safetyMenu = $(".record-safety-actions", $("#drawer"));
    if (primary && safetyMenu && !safetyMenu.querySelector(".v82-delete-record")) {
      if (r.status === "cancelled") {
        primary.innerHTML = `<button class="secondary v82-reopen" type="button">Reopen record</button>`;
      } else {
        primary.innerHTML = `<button class="secondary danger-button v82-cancel" type="button">Cancel & close balance</button>`;
      }
      safetyMenu.innerHTML = `<button class="v82-delete-record" type="button">Delete test / duplicate</button>`;
      primary.querySelector(".v82-cancel")?.addEventListener("click", () => cancelRecordV82(r));
      primary.querySelector(".v82-reopen")?.addEventListener("click", () => reopenRecordV82(r));
      safetyMenu.querySelector(".v82-delete-record")?.addEventListener("click", () => permanentlyDeleteRecordV82(r));
      return;
    }
    const footer = $("#drawer footer");
    if (!footer || footer.querySelector(".v82-record-actions")) return;
    const actions = document.createElement("div");
    actions.className = "v82-record-actions";
    actions.innerHTML = r.status === "cancelled"
      ? `<button class="secondary v82-reopen" type="button">Reopen record</button>
         <button class="secondary danger-button v82-delete-record" type="button">Permanently delete</button>`
      : `<button class="secondary danger-button v82-cancel" type="button">Cancel & close balance</button>
         <button class="secondary v82-delete-record" type="button">Permanently delete</button>`;
    footer.prepend(actions);
    const cancel = actions.querySelector(".v82-cancel");
    const reopen = actions.querySelector(".v82-reopen");
    const remove = actions.querySelector(".v82-delete-record");
    if (cancel) cancel.onclick = () => cancelRecordV82(r);
    if (reopen) reopen.onclick = () => reopenRecordV82(r);
    if (remove) remove.onclick = () => permanentlyDeleteRecordV82(r);
  }

  openDrawer = async function (id, tab = "Overview") {
    await baseOpenDrawerV82(id, tab);
    if (state.current && state.current.id === id) enhanceDrawerV82(state.current);
  };

  renderOverview = function (r, body) {
    baseRenderOverviewV82(r, body);
    const cancellation = r.workflow_state?.cancellation;
    if (!cancellation) return;
    const banner = document.createElement("section");
    banner.className = "v82-cancelled-banner";
    banner.innerHTML = `<div><small>CANCELLED BOOKING · NO FURTHER PAYMENT DUE</small><strong>${esc(cancellation.reason || "No cancellation reason recorded")}</strong><span>${cancellation.cancellation_date ? `Cancelled ${esc(fmtDate(cancellation.cancellation_date))}` : esc(fmtDateTime(cancellation.cancelled_at))}${cancellation.cancelled_by ? ` · ${esc(cancellation.cancelled_by)}` : ""}</span><span>Unpaid balance closed: ${money(cancellation.unpaid_balance_closed || 0)} · Payment retained: ${money(cancellation.payments_retained || 0)} · No client email sent</span></div><b>Cancelled</b>`;
    body.prepend(banner);
  };

  renderCalendar = function () {
    const rows = filtered().filter(r => r.event_date && r.status !== "cancelled").sort((a, b) => a.event_date.localeCompare(b.event_date));
    const groups = {};
    rows.forEach(r => {
      const key = new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" }).format(new Date(r.event_date + "T12:00:00"));
      (groups[key] ??= []).push(r);
    });
    $("#content").innerHTML = Object.keys(groups).length
      ? `<div class="calendar-list">${Object.entries(groups).map(([month, items]) => `<section class="panel month"><div class="panel-title"><div><h2>${esc(month)}</h2><p>${items.length} dated record${items.length === 1 ? "" : "s"}</p></div></div>${items.map(r => `<button class="calendar-row" data-record="${r.id}"><time><strong>${r.event_date.slice(8, 10)}</strong><small>${new Intl.DateTimeFormat("en-GB", { weekday: "short" }).format(new Date(r.event_date + "T12:00:00"))}</small></time><span><strong>${esc(r.title)}</strong><small>${esc(r.venue_or_project || r.package_name || "")}</small></span><i class="brand-badge ${r.brand}">${esc(labels[r.brand])}</i></button>`).join("")}</section>`).join("")}</div>`
      : `<div class="panel empty"><strong>No dated active records</strong>Cancelled records are retained under their status filter but do not appear in the working calendar.</div>`;
    wireRecords();
  };

  openRecordModal = function (r = null) {
    baseOpenRecordModalV82(r);
    setTimeout(() => {
      const statusSelect = $("#form-status");
      if (!statusSelect || !r) return;
      if (r.status === "cancelled") {
        statusSelect.disabled = true;
        const label = statusSelect.closest("label");
        if (label && !label.querySelector(".v82-field-help")) {
          label.insertAdjacentHTML("beforeend", `<small class="v82-field-help">Use Reopen record to change a cancelled status.</small>`);
        }
      } else {
        statusSelect.querySelector('option[value="cancelled"]')?.remove();
      }
    }, 0);
  };

  async function voidInvoiceV82(r, invoice) {
    reasonModal(
      `Void invoice ${invoice.number}`,
      "The invoice number, document and payment history will remain in the register. Its outstanding balance becomes £0.00 and it is clearly marked VOID.",
      "Void invoice",
      async () => {
        const result = await api(`/api/invoices/${invoice.id}/void`, {
          method: "POST",
          body: JSON.stringify({ reason: value("#v82-reason").trim() })
        });
        closeModal();
        await refresh();
        toast(result.message || `${invoice.number} voided`);
        if (r) await openDrawer(r.id, "Finance");
        else await renderInvoices();
      }
    );
  }

  async function deleteInvoiceV82(r, invoice) {
    const phrase = `DELETE ${invoice.number}`;
    confirmedDeleteModal(
      `Delete mistaken invoice ${invoice.number}`,
      "Only a genuinely mistaken, unpaid invoice with no payments and no accepted quote link can be deleted. Issued, linked or paid invoices must be voided instead.",
      phrase,
      async () => {
        const result = await api(`/api/invoices/${invoice.id}/permanent-delete`, {
          method: "POST",
          body: JSON.stringify({
            reason: value("#v82-reason").trim(),
            confirmation: value("#v82-confirmation")
          })
        });
        closeModal();
        await refresh();
        toast(result.message || `${invoice.number} deleted`);
        if (r) await openDrawer(r.id, "Finance");
        else await renderInvoices();
      }
    );
  }

  function showVoidReasonV82(invoice) {
    const record = invoice.void_record || {};
    const content = $("#modal-content");
    content.innerHTML = `<div class="modal-head"><div><small>PERMANENT INVOICE RECORD</small><h2>${esc(invoice.number)} void reason</h2><p>This note is retained with the invoice and included on its PDF.</p></div><button type="button" id="close-modal">×</button></div><div class="v8982-void-reason-modal"><small>REASON RECORDED WHEN VOIDED</small><strong>${esc(record.reason || invoice.notes || "No reason was recorded")}</strong>${record.voided_at || record.voided_by ? `<span>${record.voided_at ? esc(record.voided_at) : ""}${record.voided_at && record.voided_by ? " · " : ""}${record.voided_by ? `by ${esc(record.voided_by)}` : ""}</span>` : ""}<a class="secondary" href="/api/invoices/${invoice.id}/pdf">Open retained invoice PDF</a></div><footer class="v8982-readonly-footer"><button class="primary" id="close-void-reason" type="button">Close</button></footer>`;
    $("#modal").classList.remove("hidden");
    $("#modal-overlay").classList.remove("hidden");
    $("#close-modal").onclick = $("#close-void-reason").onclick = closeModal;
  }

  function showCancellationReasonV899(invoice) {
    const record = invoice.cancellation_record || {};
    const content = $("#modal-content");
    content.innerHTML = `<div class="modal-head"><div><small>PERMANENT CANCELLATION RECORD</small><h2>${esc(invoice.number)} cancellation</h2><p>The invoice and all payments remain retained, while no further balance is due.</p></div><button type="button" id="close-modal">×</button></div><div class="v899-cancellation-reason"><small>REASON RECORDED</small><strong>${esc(record.reason || "No reason was recorded")}</strong><dl><dt>Cancellation date</dt><dd>${record.cancellation_date ? esc(fmtDate(record.cancellation_date)) : "Not recorded"}</dd><dt>Unpaid balance closed</dt><dd>${money(record.closed_balance || 0)}</dd><dt>Recorded by</dt><dd>${esc(record.cancelled_by || "Administrator")}</dd></dl><a class="secondary" href="/api/invoices/${invoice.id}/pdf">Open retained invoice PDF</a></div><footer class="v8982-readonly-footer"><button class="primary" id="close-cancellation-reason" type="button">Close</button></footer>`;
    $("#modal").classList.remove("hidden");
    $("#modal-overlay").classList.remove("hidden");
    $("#close-modal").onclick = $("#close-cancellation-reason").onclick = closeModal;
  }

  function recordRefundV899(r, invoice) {
    showModal(
      `Record refund for ${invoice.number}`,
      `<div class="full v899-refund-summary"><strong>Payment currently retained: ${money(invoice.paid)}</strong><span>This records money actually returned to the couple. It does not reopen the cancelled balance and it sends no email.</span></div>
       <label>Refund amount<input id="v899-refund-amount" type="number" min="0.01" max="${attr(invoice.paid)}" step="0.01" value="${attr(invoice.paid)}" required></label>
       <label>Refund date<input id="v899-refund-date" type="date" value="${localTodayV899()}" max="${localTodayV899()}" required></label>
       <label class="full">Reference (optional)<input id="v899-refund-reference" maxlength="120" placeholder="Bank reference or transfer note"></label>
       <label class="full">Reason<textarea id="v899-refund-reason" rows="3" required minlength="3" placeholder="Why this payment was refunded"></textarea></label>`,
      async () => {
        const result = await api(`/api/invoices/${invoice.id}/refunds`, {
          method: "POST",
          body: JSON.stringify({
            amount: Number(value("#v899-refund-amount")),
            refund_date: value("#v899-refund-date"),
            reference: value("#v899-refund-reference").trim() || null,
            reason: value("#v899-refund-reason").trim()
          })
        });
        closeModal();
        await refresh();
        toast(result.message || "Refund recorded");
        await openDrawer(r.id, "Finance");
      },
      "Refund entries are permanent accounting history and cannot be deleted from a cancelled invoice."
    );
    setModalActionLabel("Record refund");
  }

  renderFinance = function (r, body) {
    const activeInvoices = r.invoices.filter(i => !["void", "cancelled"].includes(i.status));
    const invoiced = activeInvoices.reduce((sum, invoice) => sum + Number(invoice.total || 0), 0);
    const paid = r.invoices.reduce((sum, invoice) => sum + Number(invoice.paid || 0), 0);
    body.innerHTML = `<section class="summary"><div><small>QUOTED</small><strong>${money(r.quoted_total)}</strong></div><div><small>ACTIVE INVOICES</small><strong>${money(invoiced)}</strong></div><div><small>PAYMENTS RECORDED</small><strong>${money(paid)}</strong></div></section>
      <div class="section-actions"><div><h3>Invoices & bank transfers</h3><p>Invoice numbers remain chronological—even when voided</p></div><button id="new-invoice" class="primary">＋ New invoice</button></div>
      <div class="invoice-cards">${r.invoices.map(i => {
        const isVoid = i.status === "void";
        const isCancelled = i.status === "cancelled";
        const isClosed = isVoid || isCancelled;
        const deletable = i.status === "unpaid" && Number(i.paid || 0) === 0 && !(i.payments || []).length;
        return `<article class="invoice-card ${isVoid ? "v82-void-invoice" : isCancelled ? "v899-cancelled-invoice" : ""}" data-v82-invoice="${i.id}">
          <header><div><strong>${esc(i.number)}</strong><span class="status ${statusClass(i.status)} ${isVoid ? "v82-void-status" : ""}">${esc(statusText(i.status))}</span></div><div class="file-actions"><button class="invoice-preview-button" data-preview-invoice="${i.id}" data-invoice-number="${attr(i.number)}" type="button">View invoice</button><a href="/api/invoices/${i.id}/pdf">Download PDF</a>${i.paid > 0 ? `<a href="/api/invoices/${i.id}/receipt.pdf">Receipt</a>` : ""}</div></header>
          ${isVoid ? `<div class="v82-void-strip"><strong>VOID</strong><span>This invoice is retained for the financial record and has no outstanding balance.</span></div>${i.void_record ? `<div class="v8982-void-reason"><small>REASON RECORDED WHEN VOIDED</small><strong>${esc(i.void_record.reason)}</strong><span>${i.void_record.voided_at ? esc(i.void_record.voided_at) : "Date retained in the invoice audit history"}${i.void_record.voided_by ? ` · by ${esc(i.void_record.voided_by)}` : ""}</span></div>` : ""}` : ""}
          ${isCancelled ? `<div class="v899-cancelled-strip"><strong>BOOKING CANCELLED</strong><span>No further payment is due. The invoice and payment history remain retained.</span></div>${i.cancellation_record ? `<div class="v899-cancellation-card"><small>CANCELLATION REASON</small><strong>${esc(i.cancellation_record.reason)}</strong><span>${i.cancellation_record.cancellation_date ? esc(fmtDate(i.cancellation_record.cancellation_date)) : "Date retained in audit history"} · ${money(i.cancellation_record.closed_balance || 0)} unpaid balance closed</span></div>` : ""}` : ""}
          <dl><dt>Total</dt><dd>${money(i.total)}</dd>${Number(i.refunded || 0) > 0 ? `<dt>Originally received</dt><dd>${money(i.gross_paid)}</dd><dt>Refunded</dt><dd>-${money(i.refunded)}</dd><dt>Payment retained</dt><dd>${money(i.paid)}</dd>` : `<dt>${isCancelled ? "Payment retained" : "Paid"}</dt><dd>${money(i.paid)}</dd>`}<dt>Balance due</dt><dd><strong>${money(isClosed ? 0 : i.balance)}</strong></dd><dt>Final payment due</dt><dd><strong>${isClosed ? "-" : i.due_date ? esc(fmtDate(i.due_date)) : "Not set"}</strong>${!isClosed && i.due_date_overridden ? ` <span class="agreed-date">Agreed date</span>` : ""}</dd></dl>
          ${!isClosed && Number(i.balance || 0) > 0 ? `<button class="change-due-date" data-due-invoice="${i.id}" data-due-date="${attr(i.due_date || "")}" data-standard-due="${attr(i.standard_due_date || "")}">Change final payment date</button>` : ""}
          ${i.description ? `<p>${esc(i.description)}</p>` : ""}
          <div class="payments">${(i.payments || []).map(p => `<div data-payment="${p.id}" class="${p.payment_type === "refund" ? "v899-refund-row" : ""}"><span><strong>${p.payment_type === "refund" ? `-${money(Math.abs(Number(p.amount)))}` : money(p.amount)}</strong><small>${esc(fmtDate(p.paid_date))} · ${esc(statusText(p.payment_type))}${p.notes ? ` · ${esc(p.notes)}` : ""}</small></span>${isClosed || p.payment_type === "refund" ? "" : `<button class="mini danger-text" data-action="delete-payment">Delete</button>`}</div>`).join("")}</div>
          ${!isClosed && i.balance > 0 ? `<button class="secondary full" data-payment-invoice="${i.id}" data-balance="${i.balance}">Record bank transfer</button>` : ""}
          ${isCancelled && Number(i.paid || 0) > 0 ? `<button class="secondary full v899-refund-button" data-v899-refund="${i.id}">Record refund</button>` : ""}
          <div class="v82-invoice-actions">${isVoid ? `<button class="mini" data-v82-view-void="${i.id}">View void reason</button>` : isCancelled ? `<button class="mini" data-v899-view-cancellation="${i.id}">View cancellation record</button>` : `<button class="mini danger-text" data-v82-void="${i.id}">Void invoice</button>`}${deletable ? `<button class="mini danger-text" data-v82-delete-invoice="${i.id}">Delete mistaken invoice</button>` : ""}</div>
        </article>`;
      }).join("") || `<div class="empty small-empty"><strong>No invoices yet</strong>Create the first branded invoice above.</div>`}</div>`;

    $("#new-invoice").onclick = () => newInvoice(r);
    $$('[data-preview-invoice]', body).forEach(button => button.onclick = () => showPdfPreview(`Invoice ${button.dataset.invoiceNumber}`, `/api/invoices/${button.dataset.previewInvoice}/pdf?inline=true`, `/api/invoices/${button.dataset.previewInvoice}/pdf`));
    $$('[data-payment-invoice]', body).forEach(button => button.onclick = () => recordPayment(r, button.dataset.paymentInvoice, Number(button.dataset.balance)));
    $$('[data-due-invoice]', body).forEach(button => button.onclick = () => changeInvoiceDueDate(r, button.dataset.dueInvoice, button.dataset.dueDate, button.dataset.standardDue));
    $$('[data-action="delete-payment"]', body).forEach(button => button.onclick = async () => {
      if (!confirm("Remove this payment entry? If it is the only recorded payment, the wedding will return to provisional and its calendar/date-checker reservation will be removed.")) return;
      await api(`/api/payments/${button.closest("[data-payment]").dataset.payment}`, { method: "DELETE" });
      toast("Payment removed");
      openDrawer(r.id, "Finance");
    });
    $$('[data-v82-void]', body).forEach(button => button.onclick = () => voidInvoiceV82(r, r.invoices.find(i => i.id === button.dataset.v82Void)));
    $$('[data-v82-view-void]', body).forEach(button => button.onclick = () => showVoidReasonV82(r.invoices.find(i => i.id === button.dataset.v82ViewVoid)));
    $$('[data-v899-view-cancellation]', body).forEach(button => button.onclick = () => showCancellationReasonV899(r.invoices.find(i => i.id === button.dataset.v899ViewCancellation)));
    $$('[data-v899-refund]', body).forEach(button => button.onclick = () => recordRefundV899(r, r.invoices.find(i => i.id === button.dataset.v899Refund)));
    $$('[data-v82-delete-invoice]', body).forEach(button => button.onclick = () => deleteInvoiceV82(r, r.invoices.find(i => i.id === button.dataset.v82DeleteInvoice)));
  };

  renderInvoices = async function () {
    const view = state.view;
    $("#content").innerHTML = `<div class="panel loading">Loading invoices…</div>`;
    try {
      const qs = state.brand === "all" ? "" : `?brand=${state.brand}`;
      let rows = await api(`/api/invoices${qs}`);
      rows = rows.filter(i => !state.search || `${i.number} ${i.client}`.toLowerCase().includes(state.search));
      if (state.view !== view) return;
      $("#content").innerHTML = `<article class="panel"><div class="panel-title"><div><h2>Payments & invoices</h2><p>${rows.length} invoice${rows.length === 1 ? "" : "s"} · outstanding balances are ordered by the nearest due date</p></div></div><div class="table-wrap"><div class="table invoices v82-invoice-register"><div class="table-head"><span>Invoice</span><span>Client</span><span>Brand</span><span>Issued</span><span>Final balance due</span><span>Balance</span><span>Status</span><span>Files</span><span>Actions</span></div>${rows.map(i => {
        const isVoid = i.status === "void";
        const isCancelled = i.status === "cancelled";
        const deletable = i.status === "unpaid" && Number(i.paid || 0) === 0 && !(i.payments || []).length;
        const paid = Number(i.balance || 0) <= 0 || isVoid || isCancelled;
        const dueDetail = paid ? (isVoid ? "Voided" : isCancelled ? "Cancelled · balance closed" : "Paid in full") : i.payment_due_status === "overdue" ? `${Math.abs(i.days_until_due)} day${Math.abs(i.days_until_due) === 1 ? "" : "s"} overdue` : i.payment_due_status === "due_today" ? "Due today" : i.due_date_overridden ? "Agreed date" : i.wedding_date ? "45 days before wedding" : "Invoice due date";
        return `<div class="table-row ${isVoid ? "v82-void-row" : isCancelled ? "v899-cancelled-row" : ""}"><strong>${esc(i.number)}</strong><button class="link-button" data-record="${i.booking_id}">${esc(i.client || "")}</button><span class="brand-badge ${i.brand}">${esc(labels[i.brand])}</span><span>${esc(fmtDate(i.issue_date))}</span><span class="v88-due-cell ${esc(i.payment_due_status || "no_date")}"><strong>${paid ? "-" : esc(fmtDate(i.payment_due_date))}</strong><small>${esc(dueDetail)}</small></span><strong>${money(isVoid || isCancelled ? 0 : i.balance)}</strong><span class="status ${statusClass(i.status)} ${isVoid ? "v82-void-status" : ""}">${esc(statusText(i.status))}</span><span class="file-actions"><button class="mini" data-register-preview-invoice="${i.id}" data-invoice-number="${attr(i.number)}" type="button">View</button><a href="/api/invoices/${i.id}/pdf" title="Download invoice">Download</a>${i.paid > 0 ? `<a href="/api/invoices/${i.id}/receipt.pdf" title="Download receipt">Receipt</a>` : ""}</span><span class="v82-register-actions">${isVoid ? `<button class="mini" data-v82-register-reason="${i.id}">Reason</button>` : isCancelled ? `<button class="mini" data-v899-register-cancellation="${i.id}">Cancellation</button>` : `<button class="mini danger-text" data-v82-register-void="${i.id}">Void</button>`}${deletable ? `<button class="mini danger-text" data-v82-register-delete="${i.id}">Delete</button>` : ""}</span></div>`;
      }).join("")}</div>${rows.length ? "" : `<div class="empty"><strong>No invoices yet</strong>Create one from a record's Finance tab.</div>`}</div></article>`;
      wireRecords();
      $$('[data-register-preview-invoice]').forEach(button => button.onclick = () => showPdfPreview(`Invoice ${button.dataset.invoiceNumber}`, `/api/invoices/${button.dataset.registerPreviewInvoice}/pdf?inline=true`, `/api/invoices/${button.dataset.registerPreviewInvoice}/pdf`));
      $$('[data-v82-register-void]').forEach(button => button.onclick = () => voidInvoiceV82(null, rows.find(i => i.id === button.dataset.v82RegisterVoid)));
      $$('[data-v82-register-reason]').forEach(button => button.onclick = () => showVoidReasonV82(rows.find(i => i.id === button.dataset.v82RegisterReason)));
      $$('[data-v899-register-cancellation]').forEach(button => button.onclick = () => showCancellationReasonV899(rows.find(i => i.id === button.dataset.v899RegisterCancellation)));
      $$('[data-v82-register-delete]').forEach(button => button.onclick = () => deleteInvoiceV82(null, rows.find(i => i.id === button.dataset.v82RegisterDelete)));
    } catch (error) {
      showError(error);
    }
  };

  async function resetContractV82(r) {
    reasonModal(
      "Reset accepted agreement",
      "The saved acceptance snapshot for this client will be removed and the agreement task reopened. Use this only for an incorrect signature, a test, or where corrected terms must be accepted again.",
      "Reset agreement",
      async () => {
        const result = await api(`/api/bookings/${r.id}/contract/reset`, {
          method: "POST",
          body: JSON.stringify({ reason: value("#v82-reason").trim() })
        });
        closeModal();
        toast(result.message || "Agreement reset");
        await openDrawer(r.id, "Client portal");
      }
    );
  }

  async function resetFormV82(r, formType, label) {
    reasonModal(
      `Reset ${label}`,
      "The submitted copy will be removed and its workflow task reopened so the client can submit a corrected form.",
      "Reset form",
      async () => {
        const result = await api(`/api/bookings/${r.id}/forms/${formType}/reset`, {
          method: "POST",
          body: JSON.stringify({ reason: value("#v82-reason").trim() })
        });
        closeModal();
        toast(result.message || `${label} reset`);
        await openDrawer(r.id, "Client portal");
      }
    );
  }

  async function enhancePortalV82(r, body) {
    if (!body || body.querySelector(".v82-reset-panel")) return;
    try {
      const data = await api(`/api/bookings/${r.id}/portal`);
      const bookingForm = data.submissions.find(item => item.form_type === "booking_form");
      if (r.status === "cancelled") {
        const warning = document.createElement("div");
        warning.className = "v82-portal-cancelled";
        warning.textContent = "This record is cancelled. Existing portal links have been revoked; reopen the record before creating or sending another link.";
        body.prepend(warning);
        ["#send-quote", "#generate-link", "#send-portal-email"].forEach(selector => {
          const button = $(selector, body);
          if (button) button.disabled = true;
        });
      }
      if (!data.contract && !bookingForm) return;
      const panel = document.createElement("section");
      panel.className = "v82-reset-panel";
      panel.innerHTML = `<div><strong>Correct submitted client items</strong><span>Protected reset controls for mistakes, tests or corrected information.</span></div><div class="v82-reset-actions">${data.contract ? `<button class="secondary" data-v82-reset-contract>Reset agreement</button>` : ""}${bookingForm ? `<button class="secondary" data-v82-reset-form="booking_form">Reset booking form</button>` : ""}</div>`;
      body.append(panel);
      panel.querySelector("[data-v82-reset-contract]")?.addEventListener("click", () => resetContractV82(r));
      panel.querySelector('[data-v82-reset-form="booking_form"]')?.addEventListener("click", () => resetFormV82(r, "booking_form", "Wedding Booking Form"));
    } catch (error) {
      console.error("Unable to add V8.2 reset controls", error);
    }
  }

  renderQuotePortal = async function (r, body) {
    await baseRenderQuotePortalV82(r, body);
    await enhancePortalV82(r, body);
  };

  renderClientPortal = async function (r, body) {
    await baseRenderClientPortalV82(r, body);
    await enhancePortalV82(r, body);
  };
})();
