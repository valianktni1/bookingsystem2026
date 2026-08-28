/* V8.30 - Studio-style desktop job workspace, wedding views and completion controls. */
(() => {
  "use strict";

  const baseRenderRecordsV830 = renderRecords;
  const baseNavigateV830 = navigate;
  const baseRecordNextActionV830 = recordNextAction;
  const baseOpenDrawerV830 = openDrawer;
  const today = () => new Date().toISOString().slice(0, 10);

  state.weddingListMode = new URLSearchParams(location.search).get("scope") === "all"
    ? "all" : "upcoming";

  function activeWedding(record) {
    return record.brand === "wbm" && record.kind === "wedding"
      && ["confirmed", "in_progress"].includes(record.status);
  }

  function weddingRow(record, canComplete = false) {
    return `<div class="v830-booking-row ${hasSameDateConflict(record) ? "same-date-booking" : ""}">
      <button class="v830-booking-open" data-record="${attr(record.id)}" type="button">
        <span class="client-cell"><i class="client-avatar ${record.brand}">${esc(initials(record))}</i><strong>${esc(record.title)}</strong></span>
        <span>${esc(record.venue_or_project || "Not set")}</span>
        <span class="booking-date-cell"><span>${esc(fmtDate(record.event_date))}</span>${sameDateBookingWarning(record)}</span>
        <span class="status ${recordStageClass(record)}" title="${attr(recordStage(record).help || "")}">${esc(recordStageLabel(record))}</span>
        <strong>${money(record.quoted_total)}</strong>
      </button>
      ${canComplete ? `<button class="v830-list-complete" data-complete-wedding="${attr(record.id)}" type="button">✓ Mark complete</button>` : ""}
    </div>`;
  }

  function renderWeddingRecordsV830() {
    const all = state.records.filter(record => record.kind === "wedding"
      && !["enquiry", "quoted"].includes(record.status)
      && (state.brand === "all" || record.brand === state.brand)
      && (!state.search || `${record.title} ${record.venue_or_project || ""} ${record.package_name || ""} ${record.client?.email || ""}`.toLowerCase().includes(state.search)));
    const active = all.filter(activeWedding);
    const upcoming = active.filter(record => record.event_date && record.event_date >= today())
      .sort((a, b) => a.event_date.localeCompare(b.event_date));
    const awaitingCompletion = active.filter(record => record.event_date && record.event_date < today())
      .sort((a, b) => b.event_date.localeCompare(a.event_date));
    const allBookings = [...all].sort((a, b) => String(b.event_date || "").localeCompare(String(a.event_date || "")));
    const showingAll = state.weddingListMode === "all" || state.archived;
    const rows = showingAll
      ? allBookings.filter(record => state.status === "all" || record.status === state.status)
      : upcoming;
    const statuses = ["all", "confirmed", "in_progress", "completed", "cancelled"];

    $("#content").innerHTML = `<section class="v830-wedding-switcher" aria-label="Wedding booking view">
      <button class="${showingAll ? "" : "active"}" data-wedding-mode="upcoming" type="button"><i>♡</i><span><strong>Upcoming weddings</strong><small>${upcoming.length} booked date${upcoming.length === 1 ? "" : "s"}</small></span></button>
      <button class="${showingAll ? "active" : ""}" data-wedding-mode="all" type="button"><i>☷</i><span><strong>All bookings</strong><small>${all.length} retained record${all.length === 1 ? "" : "s"}</small></span></button>
    </section>
    ${!showingAll && awaitingCompletion.length ? `<section class="v830-completion-queue"><header><div><small>READY TO CLOSE</small><h2>Past weddings awaiting completion</h2><p>Mark these complete when all of your work for the couple is finished. Nothing is deleted or emailed.</p></div><b>${awaitingCompletion.length}</b></header><div>${awaitingCompletion.map(record => weddingRow(record, true)).join("")}</div></section>` : ""}
    <article class="panel v830-wedding-list"><div class="tools"><div><strong>${showingAll ? "All wedding bookings" : "Upcoming weddings"}</strong><small>${showingAll ? "Completed and cancelled weddings remain safely retained here." : "Your next active weddings in date order."}</small></div>${showingAll ? `<div class="filter-pills">${statuses.map(status => `<button data-status="${status}" class="${state.status === status ? "active" : ""}">${status === "all" ? "Every status" : statusText(status)}</button>`).join("")}</div>` : `<span class="v830-upcoming-count">${upcoming.length} upcoming</span>`}<label class="archive-switch"><input id="archive-toggle" type="checkbox" ${state.archived ? "checked" : ""}> Archived</label></div>
      <div class="table-wrap"><div class="v830-booking-table"><div class="v830-booking-head"><span>Client</span><span>Venue</span><span>Wedding date</span><span>Status</span><span>Value</span></div>${rows.map(record => weddingRow(record)).join("")}</div>${rows.length ? "" : `<div class="empty"><strong>${showingAll ? "No wedding bookings found" : "No upcoming weddings"}</strong>${showingAll ? "Try another status or clear the search." : "Your next secured wedding will appear here automatically."}</div>`}</div>
    </article>`;

    $$('[data-wedding-mode]', $("#content")).forEach(button => button.onclick = () => {
      state.weddingListMode = button.dataset.weddingMode;
      state.status = "all";
      const url = new URL(location.href);
      if (state.weddingListMode === "all") url.searchParams.set("scope", "all");
      else url.searchParams.delete("scope");
      history.replaceState(history.state, "", `${url.pathname}${url.search}`);
      renderRecords();
    });
    $$('[data-status]', $("#content")).forEach(button => button.onclick = () => {
      state.status = button.dataset.status;
      renderRecords();
    });
    const archive = $("#archive-toggle");
    if (archive) archive.onchange = async () => {
      state.archived = archive.checked;
      if (state.archived) state.weddingListMode = "all";
      await refresh();
      renderRecords();
    };
    wireRecords();
    $$('[data-complete-wedding]', $("#content")).forEach(button => button.onclick = event => {
      event.stopPropagation();
      const record = state.records.find(item => item.id === button.dataset.completeWedding);
      if (record) completeWeddingV830(record, {returnToList: true});
    });
  }

  renderRecords = function () {
    if (state.view !== "weddings") return baseRenderRecordsV830();
    renderWeddingRecordsV830();
  };

  navigate = async function (view, options = {}) {
    if (view === "weddings" && state.view !== "weddings") {
      state.weddingListMode = "upcoming";
      state.status = "all";
    }
    return baseNavigateV830(view, options);
  };

  recordNextAction = function (record, portal) {
    if (record.status === "completed") return {
      title: "This wedding is completed",
      detail: "The complete booking, invoices, forms, emails and files remain safely retained.",
      tab: "Overview", action: "view", label: "Review completed wedding", quiet: true,
    };
    return baseRecordNextActionV830(record, portal);
  };

  async function completeWeddingV830(record, options = {}) {
    const future = Boolean(record.event_date && record.event_date >= today());
    const warning = future
      ? `\n\nThis wedding date is ${fmtDate(record.event_date)}, which has not passed yet.` : "";
    if (!confirm(`Mark ${record.title} as completed?${warning}\n\nIt will leave Upcoming Weddings but remain under All Bookings. Nothing is deleted, archived or emailed.`)) return;
    try {
      await api(`/api/bookings/${record.id}/complete`, {method: "POST"});
      await refresh();
      toast("Wedding marked complete · no email sent");
      if (options.returnToList) renderRecords();
      else await openDrawer(record.id, "Overview");
    } catch (error) { toast(error.message, "error"); }
  }

  async function reopenCompletedWeddingV830(record) {
    if (!confirm(`Reopen ${record.title} as an active wedding?\n\nIt will return to Upcoming Weddings if its date is still ahead. No email will be sent.`)) return;
    try {
      await api(`/api/bookings/${record.id}/reopen-completed`, {method: "POST"});
      await refresh();
      toast("Wedding reopened · no email sent");
      await openDrawer(record.id, "Overview");
    } catch (error) { toast(error.message, "error"); }
  }

  function decorateCompletionControl() {
    const record = state.current;
    const host = $(".record-primary-actions", $("#drawer"));
    if (!record || !host || host.querySelector("[data-v830-completion]")) return;
    if (activeWedding(record)) {
      host.insertAdjacentHTML("afterbegin", `<button class="primary v830-complete-wedding" data-v830-completion type="button">✓ Mark wedding complete</button>`);
      host.querySelector("[data-v830-completion]").onclick = () => completeWeddingV830(record);
    } else if (record.status === "completed") {
      host.insertAdjacentHTML("afterbegin", `<button class="secondary v830-reopen-wedding" data-v830-completion type="button">↶ Reopen completed wedding</button>`);
      host.querySelector("[data-v830-completion]").onclick = () => reopenCompletedWeddingV830(record);
    }
  }

  openDrawer = async function (id, tab = "Overview", options = {}) {
    await baseOpenDrawerV830(id, tab, options);
    decorateCompletionControl();
  };

  const drawerObserver = new MutationObserver(() => {
    if (!$("#drawer")?.classList.contains("hidden")) decorateCompletionControl();
  });
  if ($("#drawer")) drawerObserver.observe($("#drawer"), {childList: true, subtree: true, attributes: true});

  function workspaceFactsV830(record) {
    const portal = state.currentPortal || {};
    const submissions = portal.submissions || [];
    const activeInvoices = (record.invoices || []).filter(invoice => !["void", "cancelled"].includes(invoice.status));
    const outstanding = activeInvoices.reduce((sum, invoice) => sum + Number(invoice.balance || 0), 0);
    const paid = activeInvoices.reduce((sum, invoice) => sum + Number(invoice.paid || 0), 0);
    const bookingForm = submissions.find(item => item.form_type === "booking_form");
    const finalTimings = submissions.find(item => item.form_type === "final_timings");
    const contract = portal.contract || null;
    const agreementComplete = Boolean(contract && (contract.is_legacy_import || contract.fully_signed || contract.supplier_signed_at));
    const quoteSent = (portal.emails || []).some(email => email.template_key === "quote" && email.status === "sent");
    return {portal, activeInvoices, outstanding, paid, bookingForm, finalTimings, contract, agreementComplete, quoteSent};
  }

  function workflowStep(label, detail, done, tab, attention = false) {
    return `<button class="${done ? "done" : attention ? "current" : "waiting"}" data-job-tab="${tab}" type="button"><i>${done ? "✓" : attention ? "!" : "○"}</i><span><strong>${esc(label)}</strong><small>${esc(detail)}</small></span><b>›</b></button>`;
  }

  function summaryCard(icon, title, status, detail, tab, tone = "") {
    return `<button class="v830-summary-card ${tone}" data-job-tab="${tab}" type="button"><i>${icon}</i><span><small>${esc(title)}</small><strong>${esc(status)}</strong><em>${esc(detail)}</em></span><b>›</b></button>`;
  }

  async function loadJobMailV830(record, body, fallbackEmails) {
    const host = $("[data-job-mail-list]", body);
    if (!host) return;
    try {
      const conversation = await api(`/api/bookings/${record.id}/conversation?limit=8`);
      if (!host.isConnected) return;
      const messages = (conversation.messages || []).slice(0, 8);
      host.innerHTML = messages.length ? messages.map(message => `<button data-job-tab="Journey" type="button"><i class="${message.direction === "received" ? "received" : "sent"}">${message.direction === "received" ? "←" : "→"}</i><span><strong>${esc(message.subject || "(No subject)")}</strong><small>${message.direction === "received" ? "Received from couple" : `Sent by you · ${esc(emailEngagementShort(message))}`} · ${esc(fmtDateTime(message.date))}</small></span><b>View</b></button>`).join("") : `<div class="empty small-empty"><strong>No email conversation yet</strong>Messages linked to this couple will appear here.</div>`;
      $$('[data-job-tab]', host).forEach(button => button.onclick = () => selectRecordTab(record, button.dataset.jobTab, true));
      const count = $("[data-job-mail-count]", body);
      if (count) count.textContent = `${conversation.received_count || 0} received · ${conversation.sent_count || 0} sent`;
    } catch (_) {
      if (!host.isConnected) return;
      host.innerHTML = fallbackEmails.length ? fallbackEmails.slice(0, 6).map(email => `<button data-job-tab="Journey" type="button"><i class="${email.status === "sent" ? "sent" : "failed"}">${email.status === "sent" ? "→" : "!"}</i><span><strong>${esc(email.subject || statusText(email.template_key))}</strong><small>${esc(statusText(email.status))}${email.status === "sent" ? ` · ${esc(emailEngagementShort(email))}` : ""} · ${esc(fmtDateTime(email.sent_at))}</small></span><b>View</b></button>`).join("") : `<div class="empty small-empty"><strong>Email summary unavailable</strong>Open Journey to view the retained communication history.</div>`;
      $$('[data-job-tab]', host).forEach(button => button.onclick = () => selectRecordTab(record, button.dataset.jobTab, true));
    }
  }

  renderOverview = function (record, body) {
    const facts = workspaceFactsV830(record);
    const directions = venueDirections(record);
    const openTasks = (record.tasks || []).filter(task => !task.completed);
    const submissions = facts.portal.submissions || [];
    const files = record.documents || [];
    const emails = [...(facts.portal.emails || [])].sort((a, b) => String(b.sent_at || "").localeCompare(String(a.sent_at || "")));
    const quoteStatus = facts.portal.quote ? "Accepted" : facts.quoteSent ? "Sent · awaiting choice" : "Not sent";
    const agreementStatus = facts.agreementComplete ? "Signed by both" : facts.contract ? "Your signature needed" : "Waiting";
    const completion = record.workflow_state?.completion || {};
    const legacy = record.legacy_source === "studio_ninja" ? `<section class="legacy-banner"><strong>Imported safely from Studio Ninja · protected communication</strong><span>Original reference: ${esc(record.legacy_id || "Not supplied")}</span><em>General automatic emails remain blocked. This desktop view changes presentation only.</em></section>` : "";
    const cancelled = record.workflow_state?.cancellation;
    const cancellationBanner = cancelled ? `<section class="v82-cancelled-banner"><div><small>CANCELLED BOOKING · NO FURTHER PAYMENT DUE</small><strong>${esc(cancelled.reason || "No cancellation reason recorded")}</strong><span>${cancelled.cancellation_date ? `Cancelled ${esc(fmtDate(cancelled.cancellation_date))}` : esc(fmtDateTime(cancelled.cancelled_at))} · No client email sent</span></div><b>Cancelled</b></section>` : "";
    const completedBanner = record.status === "completed" ? `<section class="v830-completed-banner"><i>✓</i><span><small>COMPLETED WEDDING</small><strong>All records remain safely retained</strong><em>${completion.completed_at ? `Marked complete ${esc(fmtDateTime(completion.completed_at))}` : "This wedding no longer appears under Upcoming Weddings."}</em></span></section>` : "";

    body.innerHTML = `${legacy}${cancellationBanner}${completedBanner}<section class="v830-job-board">
      <div class="v830-job-left">
        <article class="v830-job-panel v830-workflow-panel"><header><div><small>WORKFLOW</small><h3>Wedding progress</h3></div><span>${openTasks.length} thing${openTasks.length === 1 ? "" : "s"} to do</span></header><div class="v830-workflow-list">
          ${workflowStep("Enquiry received", "Client and wedding details retained", true, "Overview")}
          ${workflowStep("Package quote", facts.portal.quote ? "Accepted by the couple" : facts.quoteSent ? "Sent and waiting" : "Prepare and send", Boolean(facts.portal.quote), "Journey", !facts.quoteSent)}
          ${workflowStep("First payment", facts.paid > 0 ? `${money(facts.paid)} recorded` : "Not recorded", facts.paid > 0 || Boolean(record.deposit_paid_date), "Payments", Boolean(facts.portal.quote && facts.paid <= 0))}
          ${workflowStep("Wedding Booking Form", facts.bookingForm ? `Submitted ${fmtDateTime(facts.bookingForm.submitted_at)}` : "Waiting for couple", Boolean(facts.bookingForm), "Journey")}
          ${workflowStep("Agreement", agreementStatus, facts.agreementComplete, "Journey", Boolean(facts.contract && !facts.agreementComplete))}
          ${workflowStep("Final wedding timings", facts.finalTimings ? "Submitted and retained" : "Waiting until final planning", Boolean(facts.finalTimings), "Journey")}
          ${workflowStep("Job complete", record.status === "completed" ? "Wedding marked complete" : "Complete after all work is finished", record.status === "completed", "Overview")}
        </div></article>
        <article class="v830-job-panel v830-mail-panel"><header><div><small>MAIL</small><h3>Conversation with ${esc(record.title)}</h3></div><span data-job-mail-count>Loading…</span></header><div class="v830-mail-list" data-job-mail-list><div class="loading">Loading this couple's emails…</div></div><footer><button class="secondary" data-job-tab="Journey" type="button">Open complete conversation</button></footer></article>
      </div>
      <div class="v830-job-right">
        <div class="v830-top-cards">
          <article class="v830-info-card"><header><span>▣</span><strong>Job</strong><button class="mini" data-job-edit type="button">Edit</button></header><dl><dt>Wedding</dt><dd>${esc(record.title)}</dd><dt>Date</dt><dd>${esc(fmtDate(record.event_date))}</dd><dt>Venue</dt><dd>${directions ? `<a href="${attr(directions)}" target="_blank" rel="noopener">${esc(record.venue_or_project || record.venue_address)} ↗</a>` : esc(record.venue_or_project || "Not set")}</dd><dt>Package</dt><dd>${esc(record.package_name || "Not selected")}</dd></dl></article>
          <article class="v830-info-card"><header><span>♙</span><strong>Client</strong><button class="mini" data-job-edit type="button">Edit</button></header><dl><dt>Name</dt><dd>${esc([record.client.first_name, record.client.last_name].filter(Boolean).join(" "))}</dd>${record.client.partner_name ? `<dt>Partner</dt><dd>${esc(record.client.partner_name)}</dd>` : ""}<dt>Email</dt><dd><a href="mailto:${attr(record.client.email)}">${esc(record.client.email)}</a></dd><dt>Phone</dt><dd>${record.client.phone ? `<a href="tel:${attr(record.client.phone)}">${esc(record.client.phone)}</a>` : "Not set"}</dd></dl></article>
        </div>
        <div class="v830-summary-stack">
          ${summaryCard("£", "INVOICES & PAYMENTS", facts.outstanding > 0 ? `${money(facts.outstanding)} outstanding` : "Account clear", `${facts.activeInvoices.length} active invoice${facts.activeInvoices.length === 1 ? "" : "s"} · ${money(facts.paid)} paid`, "Payments", facts.outstanding > 0 ? "attention" : "complete")}
          ${summaryCard("✉", "QUOTE", quoteStatus, facts.portal.quote ? `${money(facts.portal.quote.total)} accepted` : "Open the complete quote and email controls", "Journey", facts.portal.quote ? "complete" : facts.quoteSent ? "" : "attention")}
          ${summaryCard("✓", "AGREEMENT", agreementStatus, facts.contract ? (facts.contract.version || "Protected agreement") : "No signed agreement recorded yet", "Journey", facts.agreementComplete ? "complete" : "attention")}
          ${summaryCard("?", "QUESTIONNAIRES & TIMINGS", `${submissions.length} submitted`, `${facts.bookingForm ? "Booking form ✓" : "Booking form waiting"} · ${facts.finalTimings ? "Final timings ✓" : "Final timings waiting"}`, "Journey", facts.bookingForm ? "complete" : "attention")}
          ${summaryCard("▤", "FILES", `${files.length} retained`, files.length ? "Invoices, agreements, forms and uploaded documents" : "No files retained yet", "Files")}
          ${summaryCard("✎", "NOTES & TASKS", `${openTasks.length} open task${openTasks.length === 1 ? "" : "s"}`, record.notes || "Open private notes and the complete activity history", "Activity", openTasks.length ? "attention" : "complete")}
        </div>
      </div>
    </section>`;

    $$('[data-job-tab]', body).forEach(button => button.onclick = () => selectRecordTab(record, button.dataset.jobTab, true));
    $$('[data-job-edit]', body).forEach(button => button.onclick = () => openRecordModal(record));
    loadJobMailV830(record, body, emails);
  };

  window.completeWeddingV830 = completeWeddingV830;
})();
