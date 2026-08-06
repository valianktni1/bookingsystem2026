/* V8.9.5 - clean, workflow-led admin booking workspace. */
(() => {
  const originalQuestionnairesV895 = renderQuestionnaires;

  normaliseRecordTab = function (tab) {
    return ({
      "Client portal": "Quote",
      "Workflow": "Overview",
      "Journey": "Quote",
      "Questionnaires": "Forms",
      "Finance": "Payments",
      "Documents": "Files",
      "Notes & activity": "Notes"
    })[tab] || tab || "Overview";
  };

  function workspaceFacts(r, portal) {
    const journey = recordJourneyFacts(r, portal);
    const activeInvoices = (r.invoices || []).filter(invoice => invoice.status !== "void");
    const voidInvoices = (r.invoices || []).filter(invoice => invoice.status === "void");
    const outstanding = activeInvoices.reduce((sum, invoice) => sum + Number(invoice.balance || 0), 0);
    const paid = (r.invoices || []).reduce((sum, invoice) => sum + Number(invoice.paid || 0), 0);
    const nextDue = activeInvoices
      .filter(invoice => Number(invoice.balance || 0) > 0 && invoice.due_date)
      .sort((a, b) => a.due_date.localeCompare(b.due_date))[0]?.due_date || r.balance_due_date;
    return { ...journey, activeInvoices, voidInvoices, outstanding, paid, nextDue };
  }

  function workspaceSections(r, portal) {
    const facts = workspaceFacts(r, portal);
    const formCount = Number(Boolean(facts.bookingForm)) + Number(Boolean(facts.contract));
    return [
      { tab: "Overview", icon: "⌂", label: "Overview", meta: `${(r.tasks || []).filter(task => !task.completed).length} to do` },
      { tab: "Quote", icon: "✉", label: "Quote & emails", meta: facts.quote ? "Accepted" : facts.quoteSent ? "Sent" : "Not sent" },
      { tab: "Payments", icon: "£", label: "Payments", meta: facts.outstanding > 0 ? money(facts.outstanding) + " due" : facts.voidInvoices.length ? `${facts.voidInvoices.length} void` : "Clear" },
      { tab: "Forms", icon: "✓", label: "Forms & agreement", meta: `${formCount}/2 complete` },
      { tab: "Files", icon: "▤", label: "Files", meta: `${(r.documents || []).length}` },
      { tab: "Notes", icon: "✎", label: "Notes & history", meta: `${(r.booking_notes || []).length}` }
    ];
  }

  recordSectionNavigation = function (selected) {
    const r = state.current;
    const portal = state.currentPortal;
    return `<nav class="record-workspace-tabs" aria-label="Booking workspace">
      ${workspaceSections(r, portal).map(section => `<button class="${section.tab === selected ? "active" : ""}" data-tab="${section.tab}"><i>${section.icon}</i><span><strong>${section.label}</strong><small>${esc(section.meta)}</small></span></button>`).join("")}
    </nav><div id="drawer-body" class="drawer-body record-workspace-body"></div>`;
  };

  selectRecordTab = function (r, tab, scroll = false) {
    const selected = normaliseRecordTab(tab);
    state.currentTab = selected;
    $$('[data-tab]', $("#drawer")).forEach(button => button.classList.toggle("active", button.dataset.tab === selected));
    renderTab(r, selected);
    if (scroll) setTimeout(() => $(".record-workspace-tabs")?.scrollIntoView({ behavior: "smooth", block: "start" }), 25);
  };

  function workflowStages(r, portal) {
    if (r.kind !== "wedding") return "";
    const facts = workspaceFacts(r, portal);
    const today = new Date().toISOString().slice(0, 10);
    const weddingDone = r.status === "completed" || Boolean(r.event_date && r.event_date < today);
    const stages = [
      { label: "Enquiry", done: true, tab: "Overview" },
      { label: "Quote", done: Boolean(facts.quote), current: !facts.quote, tab: "Quote" },
      { label: "Payment", done: facts.hasPayment, current: Boolean(facts.quote && !facts.hasPayment), tab: "Payments" },
      { label: "Booking form", done: Boolean(facts.bookingForm), current: Boolean(facts.hasPayment && !facts.bookingForm), tab: "Forms" },
      { label: "Agreement", done: Boolean(facts.contract), current: Boolean(facts.bookingForm && !facts.contract), tab: "Forms" },
      { label: "Wedding", done: weddingDone, current: Boolean(facts.contract && !weddingDone), tab: "Overview" }
    ];
    return `<nav class="record-stage-bar" aria-label="Wedding workflow">${stages.map((stage, index) => `<button class="${stage.done ? "done" : stage.current ? "current" : ""}" data-stage-tab="${stage.tab}"><i>${stage.done ? "✓" : index + 1}</i><span>${stage.label}</span></button>`).join("")}</nav>`;
  }

  function bookingSnapshot(r, portal) {
    const facts = workspaceFacts(r, portal);
    const formCount = Number(Boolean(facts.bookingForm)) + Number(Boolean(facts.contract));
    return `<section class="record-snapshot">
      <article><small>${r.kind === "wedding" ? "WEDDING DATE" : "TARGET DATE"}</small><strong>${esc(fmtDate(r.event_date))}</strong></article>
      <article><small>PACKAGE / SERVICE</small><strong>${esc(r.package_name || "Not selected")}</strong></article>
      <article class="${facts.outstanding > 0 ? "attention" : "complete"}"><small>OUTSTANDING</small><strong>${money(facts.outstanding)}</strong></article>
      <article><small>PAYMENT DUE</small><strong>${facts.outstanding > 0 ? esc(fmtDate(facts.nextDue)) : "Nothing due"}</strong></article>
      <article class="${formCount === 2 ? "complete" : "attention"}"><small>FORM & AGREEMENT</small><strong>${formCount}/2 complete</strong></article>
      <article class="${facts.voidInvoices.length ? "voided" : ""}"><small>INVOICES</small><strong>${facts.activeInvoices.length} active${facts.voidInvoices.length ? ` · ${facts.voidInvoices.length} void` : ""}</strong></article>
    </section>`;
  }

  openDrawer = async function (id, tab = "Overview") {
    try {
      const [r, portal] = await Promise.all([
        api(`/api/bookings/${id}`),
        api(`/api/bookings/${id}/portal`).catch(() => null)
      ]);
      const selected = normaliseRecordTab(tab);
      const next = recordNextAction(r, portal);
      state.current = r;
      state.currentPortal = portal;
      state.currentTab = selected;
      const directions = venueDirections(r);
      const drawer = $("#drawer");
      drawer.innerHTML = `<header class="record-command-header ${r.brand}">
        <div class="record-command-bar">
          <button id="close-drawer" class="record-back" type="button"><span>←</span> Back to bookings</button>
          <div class="record-command-actions">
            <div class="record-primary-actions"></div>
            <button id="edit-record" class="secondary" type="button">Edit details</button>
            <div class="record-more-wrap">
              <button id="record-more" class="secondary" type="button">More actions <span>⌄</span></button>
              <div id="record-actions-menu" class="record-actions-menu hidden">
                <button id="record-client-area" type="button">Open quote & client area</button>
                <button id="archive-record" type="button">${r.archived ? "Restore from archive" : "Archive record"}</button>
                <div class="record-safety-actions"></div>
              </div>
            </div>
          </div>
        </div>
        <div class="record-command-identity">
          <span class="record-avatar-large">${esc(initials(r))}</span>
          <div>
            <small>${r.legacy_source === "studio_ninja" ? "IMPORTED · MANUAL COMMUNICATION" : r.kind === "wedding" ? "WEDDING BOOKING" : "IVORY DIGITAL PROJECT"}</small>
            <div class="record-title-line"><h1>${esc(r.title)}</h1><span class="status ${statusClass(r.status)}">${esc(statusText(r.status))}</span></div>
            <p>${esc(r.venue_or_project || "Venue or project not set")} · ${esc(fmtDate(r.event_date))}</p>
            <nav class="record-contact-actions">
              <a href="mailto:${attr(r.client.email)}">✉ Email</a>
              ${r.client.phone ? `<a href="tel:${attr(r.client.phone)}">☎ Call</a>` : ""}
              ${directions ? `<a href="${attr(directions)}" target="_blank" rel="noopener">⌖ Directions</a>` : ""}
              <button id="record-portal-shortcut" type="button">↗ Client area</button>
            </nav>
          </div>
        </div>
      </header>
      <main class="record-command-main">
        ${bookingSnapshot(r, portal)}
        ${workflowStages(r, portal)}
        <section class="record-next-action ${next.quiet ? "quiet" : ""}"><i>→</i><div><small>YOUR NEXT STEP</small><strong>${esc(next.title)}</strong><span>${esc(next.detail)}</span></div>${next.label ? `<button id="next-record-action" class="${next.quiet ? "secondary" : "primary"}">${esc(next.label)}</button>` : ""}</section>
        ${recordSectionNavigation(selected)}
      </main>`;
      drawer.classList.remove("hidden");
      $("#drawer-overlay").classList.remove("hidden");
      $("#close-drawer").onclick = closeDrawer;
      $("#edit-record").onclick = () => openRecordModal(r);
      $("#archive-record").onclick = () => toggleArchive(r);
      $("#record-client-area").onclick = $("#record-portal-shortcut").onclick = () => selectRecordTab(r, "Quote", true);
      $("#record-more").onclick = event => {
        event.stopPropagation();
        $("#record-actions-menu").classList.toggle("hidden");
      };
      if ($("#next-record-action")) $("#next-record-action").onclick = () => selectRecordTab(r, next.tab, true);
      $$('[data-stage-tab]', drawer).forEach(button => button.onclick = () => selectRecordTab(r, button.dataset.stageTab, true));
      $$('[data-tab]', drawer).forEach(button => button.onclick = () => selectRecordTab(r, button.dataset.tab));
      selectRecordTab(r, selected);
    } catch (error) {
      toast(error.message, "error");
    }
  };

  renderTab = async function (r, tab, target = null) {
    const body = target || $("#drawer-body");
    const selected = normaliseRecordTab(tab);
    if (!body) return;
    if (selected === "Overview") renderOverview(r, body);
    else if (selected === "Quote") await renderQuotePortal(r, body);
    else if (selected === "Payments") renderFinance(r, body);
    else if (selected === "Forms") renderFormsAndAgreementV895(r, body);
    else if (selected === "Files") renderRecordDocuments(r, body);
    else renderNotes(r, body);
  };

  renderOverview = function (r, body) {
    const directions = venueDirections(r);
    const facts = workspaceFacts(r, state.currentPortal);
    const tasks = [...(r.tasks || [])].sort((a, b) => Number(a.completed) - Number(b.completed) || String(a.due_at || "9999").localeCompare(String(b.due_at || "9999")));
    const legacy = r.legacy_source === "studio_ninja" ? `<section class="legacy-banner"><strong>Imported safely from Studio Ninja · manual communication only</strong><span>Original reference: ${esc(r.legacy_id || "Not supplied")}</span><em>This booking remains fully visible, while automatic emails and reminders stay permanently paused.</em></section>` : "";
    const voidNotice = facts.voidInvoices.length ? `<button class="record-void-notice" data-overview-tab="Payments"><span><strong>${facts.voidInvoices.length} voided invoice${facts.voidInvoices.length === 1 ? "" : "s"} retained</strong><small>They remain visible for your records and have no outstanding balance.</small></span><b>View payments →</b></button>` : "";
    body.innerHTML = `${legacy}${voidNotice}<div class="record-overview-grid">
      <section class="record-overview-main">
        <article class="detail"><header><h3>Couple / client</h3><button class="mini" data-overview-edit>Edit</button></header><dl><dt>Name</dt><dd>${esc([r.client.first_name, r.client.last_name].filter(Boolean).join(" "))}</dd>${r.client.partner_name ? `<dt>Partner</dt><dd>${esc(r.client.partner_name)}</dd>` : ""}<dt>Email</dt><dd><a href="mailto:${attr(r.client.email)}">${esc(r.client.email)}</a></dd><dt>Phone</dt><dd>${r.client.phone ? `<a href="tel:${attr(r.client.phone)}">${esc(r.client.phone)}</a>` : "Not set"}</dd><dt>Address</dt><dd>${esc(r.client.address || "Not set")}</dd></dl></article>
        <article class="detail"><header><h3>${r.kind === "wedding" ? "Wedding" : "Project"}</h3><button class="mini" data-overview-edit>Edit</button></header><dl><dt>Date</dt><dd>${esc(fmtDate(r.event_date))}</dd><dt>${r.kind === "wedding" ? "Venue" : "Project"}</dt><dd>${directions ? `<a class="directions-link" href="${attr(directions)}" target="_blank" rel="noopener">${esc(r.venue_or_project || r.venue_address)} ↗</a>` : esc(r.venue_or_project || "Not set")}${r.venue_address && r.venue_address !== r.venue_or_project ? `<small>${esc(r.venue_address)}</small>` : ""}</dd><dt>Package</dt><dd>${esc(r.package_name || "Not selected")}</dd><dt>Quoted value</dt><dd>${money(r.quoted_total)}</dd></dl></article>
        <article class="detail"><header><h3>Main notes</h3><button class="mini" data-overview-edit>Edit</button></header><p class="preline">${esc(r.notes || "No main notes added yet.")}</p></article>
      </section>
      <aside class="record-overview-side"><section class="overview-task-panel"><header><div><small>PRIVATE WORKFLOW</small><h3>Things to do</h3></div><button id="overview-add-task" class="secondary">＋ Add</button></header><div class="task-list">${tasks.map(task => taskRow(task)).join("") || `<div class="empty small-empty"><strong>Nothing needs doing</strong>You are all caught up.</div>`}</div></section></aside>
    </div>`;
    $$('[data-overview-edit]', body).forEach(button => button.onclick = () => openRecordModal(r));
    $$('[data-overview-tab]', body).forEach(button => button.onclick = () => selectRecordTab(r, button.dataset.overviewTab));
    wireTaskActions(body);
    $("#overview-add-task", body).onclick = () => showModal("Add something to do", `<label class="full">What needs doing?<input id="task-title" required placeholder="Call the venue or check a detail"></label><label class="full">When is it due?<input id="task-due" type="datetime-local"></label>`, async () => {
      await api(`/api/bookings/${r.id}/tasks`, { method: "POST", body: JSON.stringify({ title: value("#task-title").trim(), due_at: nullable(value("#task-due")) }) });
      closeModal();
      toast("Added to things to do");
      openDrawer(r.id, "Overview");
    }, "This is a private reminder for you and never emails the client.");
  };

  function renderFormsAndAgreementV895(r, body) {
    const portal = state.currentPortal || {};
    const bookingForm = (portal.submissions || []).find(item => item.form_type === "booking_form");
    const contract = portal.contract;
    const answerHost = document.createElement("div");
    originalQuestionnairesV895(r, answerHost);
    body.innerHTML = `<section class="forms-status-grid">
      <article class="${bookingForm ? "complete" : "waiting"}"><i>${bookingForm ? "✓" : "1"}</i><span><small>WEDDING BOOKING FORM</small><strong>${bookingForm ? "Completed" : "Waiting for client"}</strong><em>${bookingForm ? esc(fmtDateTime(bookingForm.submitted_at)) : "Answers will appear below when submitted."}</em></span></article>
      <article class="${contract ? "complete" : "waiting"}"><i>${contract ? "✓" : "2"}</i><span><small>AGREEMENT</small><strong>${contract ? "Signed and accepted" : "Waiting for client"}</strong><em>${contract ? `${esc(contract.accepted_name)} · ${esc(fmtDateTime(contract.accepted_at))}` : "The agreement follows the booking form."}</em></span></article>
    </section>
    ${contract ? `<section class="agreement-summary"><div><small>ACCEPTED AGREEMENT</small><strong>${esc(contract.version || "Saved agreement")}</strong><span>Accepted by ${esc(contract.accepted_name)} using ${esc(contract.accepted_email || r.client.email)} on ${esc(fmtDateTime(contract.accepted_at))}.</span></div><b>Protected record</b></section>` : ""}
    <div class="forms-client-controls"><span>Need to resend their link or correct a submitted item?</span><button id="forms-open-client-area" class="secondary">Open client-area controls</button></div>
    <div class="forms-answer-host">${answerHost.innerHTML}</div>`;
    $("#forms-open-client-area", body).onclick = () => selectRecordTab(r, "Quote");
  }
})();
