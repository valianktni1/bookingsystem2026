/* V8.11 - browser navigation, Today queues and simplified booking workflow. */
(() => {
  "use strict";

  const workspaceViews = new Set([
    "dashboard", "enquiries", "weddings", "projects", "calendar", "workflows",
    "mail", "invoices", "documents", "forms", "bookingforms", "packages",
    "communications", "settings"
  ]);
  const sectionSlugs = {
    Overview: "overview",
    Journey: "journey",
    Payments: "payments",
    Files: "files",
    Activity: "activity",
  };
  const slugSections = Object.fromEntries(Object.entries(sectionSlugs).map(([key, value]) => [value, key]));
  const queueCopy = {
    communication_failures: ["Communication problems", "Emails that need a retry or your review", "!"],
    client_updates: ["New client updates", "Quote acceptances, forms, signed agreements and replies", "●"],
    overdue_payments: ["Overdue payments", "Payment date has passed", "!"],
    new_enquiries: ["New enquiries", "Review the details and prepare the quote", "◎"],
    quotes_waiting: ["Quotes awaiting acceptance", "The couple has not chosen their package", "✉"],
    accepted_payment: ["Accepted · payment needed", "Record the first payment when it arrives", "£"],
    forms_waiting: ["Booking forms outstanding", "Secured couples still completing their details", "✓"],
    agreements_waiting: ["Agreements outstanding", "Waiting for a signature or countersignature", "✎"],
    payments_due: ["Payments due soon", "Due within the next 60 days", "£"],
    final_calls: ["Final-detail calls", "Private telephone reminders due soon", "☎"],
  };
  const queueOrder = Object.keys(queueCopy);
  const actionQueueOrder = [
    "communication_failures", "client_updates", "overdue_payments",
    "new_enquiries", "final_calls",
  ];
  const waitingQueueOrder = [
    "quotes_waiting", "accepted_payment", "forms_waiting",
    "agreements_waiting", "payments_due",
  ];
  const baseNavigateV811 = navigate;
  const baseOpenDrawerV811 = openDrawer;
  const baseCloseDrawerV811 = closeDrawer;
  const baseRenderTabV811 = renderTab;
  const baseRefreshV811 = refresh;
  const baseStatusTextV811 = statusText;
  let applyingRoute = false;
  let initialRouteApplied = false;
  let workflowQueueCache = null;
  let searchIndexCache = null;
  let dashboardRenderNumber = 0;
  let searchTimer = null;

  function canonicalSection(tab) {
    return ({
      Quote: "Journey", Journey: "Journey", Forms: "Journey", Questionnaires: "Journey",
      "Client portal": "Journey", Workflow: "Overview", Finance: "Payments",
      Documents: "Files", Notes: "Activity", "Notes & activity": "Activity",
    })[tab] || (sectionSlugs[tab] ? tab : "Overview");
  }

  function legacySection(section) {
    return ({ Journey: "Quote", Activity: "Notes" })[canonicalSection(section)] || canonicalSection(section);
  }

  function pathAndQuery(url) {
    return `${url.pathname}${url.search}`;
  }

  function workspaceUrl(view = state.view) {
    const url = new URL(`/${workspaceViews.has(view) ? view : "dashboard"}`, location.origin);
    if (state.brand && state.brand !== "all") url.searchParams.set("brand", state.brand);
    if (state.search) url.searchParams.set("q", state.search);
    if (state.status && state.status !== "all") url.searchParams.set("status", state.status);
    if (state.archived) url.searchParams.set("archived", "1");
    return pathAndQuery(url);
  }

  function bookingUrl(id, section = "Overview") {
    const selected = canonicalSection(section);
    const url = new URL(`/bookings/${encodeURIComponent(id)}/${sectionSlugs[selected]}`, location.origin);
    if (state.brand && state.brand !== "all") url.searchParams.set("brand", state.brand);
    return pathAndQuery(url);
  }

  function rememberScroll() {
    if (!history.state?.wbm) return;
    history.replaceState({ ...history.state, scrollY: window.scrollY }, "", location.href);
  }

  function writeRoute(target, options = {}) {
    const current = `${location.pathname}${location.search}`;
    const nextState = { wbm: true, ...(options.state || {}) };
    if (current === target || options.replace) {
      history.replaceState({ ...history.state, ...nextState }, "", target);
      return;
    }
    rememberScroll();
    history.pushState(nextState, "", target);
  }

  function parseRoute() {
    const parts = location.pathname.split("/").filter(Boolean);
    const params = new URLSearchParams(location.search);
    const common = {
      brand: ["all", "wbm", "ivory"].includes(params.get("brand")) ? params.get("brand") : "all",
      search: (params.get("q") || "").toLowerCase(),
      status: params.get("status") || "all",
      archived: params.get("archived") === "1",
    };
    if (parts[0] === "bookings" && parts[1]) {
      return { ...common, bookingId: decodeURIComponent(parts[1]), section: slugSections[parts[2]] || "Overview" };
    }
    return { ...common, view: workspaceViews.has(parts[0]) ? parts[0] : "dashboard" };
  }

  function setBrandChrome() {
    $("#brand-label").textContent = labels[state.brand];
    $("#brand-dot").className = `dot ${state.brand}`;
  }

  function parentViewForRecord(record) {
    if (!record) return "weddings";
    if (record.kind === "digital") return "projects";
    return ["enquiry", "quoted"].includes(record.status) ? "enquiries" : "weddings";
  }

  async function applyCurrentRoute(options = {}) {
    if ($("#app")?.classList.contains("hidden")) return;
    const route = parseRoute();
    applyingRoute = true;
    try {
      state.brand = route.brand;
      state.search = route.search;
      state.status = route.status;
      state.archived = route.archived;
      setBrandChrome();
      $("#search").value = route.search;
      if (route.bookingId) {
        const known = state.records.find(record => record.id === route.bookingId);
        await baseNavigateV811(parentViewForRecord(known));
        await baseOpenDrawerV811(route.bookingId, legacySection(route.section));
        if (state.current) {
          const parent = parentViewForRecord(state.current);
          if (state.view !== parent) await baseNavigateV811(parent);
          await selectRecordTab(state.current, route.section, false, { replace: true });
          decorateOpenRecord(state.current);
        }
      } else {
        baseCloseDrawerV811();
        await baseNavigateV811(route.view);
        state.status = route.status;
        state.archived = route.archived;
        if (state.archived) await baseRefreshV811();
        render();
      }
      if (options.replace || !history.state?.wbm) {
        history.replaceState({ ...history.state, wbm: true, scrollY: history.state?.scrollY || 0 }, "", location.href);
      }
      requestAnimationFrame(() => window.scrollTo(0, Number(history.state?.scrollY || 0)));
    } finally {
      applyingRoute = false;
      initialRouteApplied = true;
    }
  }

  navigate = async function (view, options = {}) {
    await baseNavigateV811(view);
    if (!applyingRoute && !options.fromRoute) {
      state.status = "all";
      writeRoute(workspaceUrl(view), { replace: Boolean(options.replace) });
    }
  };

  refresh = async function () {
    const result = await baseRefreshV811();
    workflowQueueCache = null;
    searchIndexCache = null;
    return result;
  };

  statusText = function (status) {
    return ({
      enquiry: "New enquiry",
      quoted: "Quote sent",
      confirmed: "Secured",
      in_progress: "Ready for wedding",
      completed: "Completed",
      cancelled: "Cancelled",
    })[status] || baseStatusTextV811(status);
  };

  function recordSectionMeta(r, portal) {
    const facts = recordJourneyFacts(r, portal || {});
    const activeInvoices = (r.invoices || []).filter(invoice => invoice.status !== "void");
    const outstanding = activeInvoices.reduce((sum, invoice) => sum + Number(invoice.balance || 0), 0);
    const agreementComplete = Boolean(facts.contract && (
      facts.contract.is_legacy_import || facts.contract.fully_signed || facts.contract.supplier_signed_at
    ));
    return {
      Overview: `${(r.tasks || []).filter(task => !task.completed).length} to do`,
      Journey: `${Number(Boolean(facts.quote)) + Number(Boolean(facts.bookingForm)) + Number(agreementComplete)}/3 complete`,
      Payments: outstanding > 0 ? `${money(outstanding)} due` : "Clear",
      Files: `${(r.documents || []).length}`,
      Activity: `${(r.activity || []).length} events`,
    };
  }

  recordSectionNavigation = function (selected) {
    const r = state.current;
    const active = canonicalSection(selected);
    const meta = recordSectionMeta(r, state.currentPortal);
    const sections = [
      ["Overview", "⌂", "Overview"],
      ["Journey", "✓", "Journey"],
      ["Payments", "£", "Payments"],
      ["Files", "▤", "Files"],
      ["Activity", "◷", "Activity"],
    ];
    return `<nav class="record-workspace-tabs v811-tabs" aria-label="Booking workspace">
      ${sections.map(([tab, icon, label]) => `<button class="${tab === active ? "active" : ""}" data-tab="${tab}"><i>${icon}</i><span><strong>${label}</strong><small>${esc(meta[tab])}</small></span></button>`).join("")}
    </nav><div id="drawer-body" class="drawer-body record-workspace-body"></div>`;
  };

  async function renderJourneyV811(r, body) {
    const stage = recordStage(r);
    const facts = recordJourneyFacts(r, state.currentPortal || {});
    const agreementComplete = Boolean(facts.contract && (
      facts.contract.is_legacy_import || facts.contract.fully_signed || facts.contract.supplier_signed_at
    ));
    const progress = [
      ["Quote", Boolean(facts.quote)], ["Payment", facts.hasPayment],
      ["Booking form", Boolean(facts.bookingForm)], ["Agreement", agreementComplete],
    ];
    body.innerHTML = `<div class="v811-journey">
      <section class="v828-journey-summary ${attr(stage.tone || "neutral")}"><div><small>CURRENT JOURNEY STAGE</small><h3>${esc(stage.label)}</h3><p>${esc(stage.help || "The stored booking facts determine this status automatically.")}</p></div><div class="v828-progress-pills">${progress.map(([label, done]) => `<span class="${done ? "done" : "waiting"}"><i>${done ? "✓" : "○"}</i>${esc(label)}</span>`).join("")}</div></section>
      <section class="v811-journey-block v811-journey-quote"><header><div><small>STEP 1</small><h3>Quote, client access and emails</h3></div><span>Everything sent to the couple is recorded here</span></header><div data-v811-quote></div></section>
      <section class="v811-journey-block v811-journey-forms"><header><div><small>STEPS 2 & 3</small><h3>Wedding Booking Form and agreement</h3></div><span>The couple's answers and protected signatures</span></header><div data-v811-forms></div></section>
    </div>`;
    const quoteHost = $("[data-v811-quote]", body);
    const formHost = $("[data-v811-forms]", body);
    await baseRenderTabV811(r, "Quote", quoteHost);
    await baseRenderTabV811(r, "Forms", formHost);
  }

  function activityLabel(action) {
    return ({
      website_enquiry: "Enquiry received",
      create: "Booking created",
      update: "Booking details updated",
      prepare_quote: "Quote prepared",
      send_quote: "Quote sent",
      quote_link_accessed: "Quote link first accessed",
      accept_quote: "Quote accepted",
      create_invoice: "Invoice created",
      change_invoice_due_date: "Payment date changed",
      record_payment: "Payment recorded",
      delete_payment: "Payment entry removed",
      submit_form: "Wedding Booking Form submitted",
      review_final_timings: "Final Wedding Timings reviewed",
      accept_contract: "Agreement signed by the client",
      countersign_contract: "Agreement countersigned",
      send_contract_completion_email: "Completed agreement emailed",
      create_client_link: "Secure client link created",
      create_manual_client_link: "Manual secure client link created",
      create_task: "Private task added",
      update_task: "Private task updated",
      delete_task: "Private task deleted",
      upload_document: "File uploaded",
      delete_document: "File deleted",
      archive: "Record archived",
      restore: "Record restored",
      cancel_booking: "Booking cancelled",
      reopen_booking: "Booking reopened",
      complete_booking: "Wedding marked complete",
      reopen_completed_booking: "Completed wedding reopened",
    })[action] || baseStatusTextV811(action).replace(/\b\w/g, character => character.toUpperCase());
  }

  function activityDetail(details) {
    if (!details || typeof details !== "object") return "";
    const preferred = ["subject", "template", "invoice", "amount", "form_type", "reason", "name"];
    return preferred.filter(key => details[key] !== undefined && details[key] !== null)
      .map(key => `${baseStatusTextV811(key)}: ${details[key]}`).join(" · ");
  }

  function friendlyEmailFailure(error) {
    const raw = String(error || "");
    if (/\b454\b.*\b4\.3\.0\b.*try again later/i.test(raw)) {
      return "Hostinger temporarily refused this message and asked the system to try again later. The booking action still completed safely.";
    }
    return raw;
  }

  function renderActivityV811(r, body) {
    const portal = state.currentPortal || {};
    const latestContractEmail = (portal.emails || []).find(email => email.template_key === "contract_completed");
    const emailEvents = (portal.emails || []).map(email => ({
      at: email.sent_at,
      type: email.status === "sent" || email.status === "recovered" ? "sent" : "failed",
      label: email.status === "sent" ? "Email sent successfully" : email.status === "recovered" ? "Earlier email failure recovered" : "Email failed",
      detail: `${email.subject} · ${email.recipient}${email.error ? ` · ${friendlyEmailFailure(email.error)}` : ""}`,
      retryContractCompletion: email === latestContractEmail && email.status === "failed",
      retryEmailId: email.status === "failed" && email.retryable ? email.id : null,
    }));
    const noteEvents = (r.booking_notes || []).map(note => ({
      at: note.created_at, type: "note", label: "Private note", detail: note.body, noteId: note.id,
    }));
    const auditEvents = (r.activity || [])
      .filter(event => !["add_note", "delete_note", "send_email", "send_client_email", "send_manual_email"].includes(event.action))
      .map(event => ({
        at: event.created_at, type: "audit",
        label: event.action === "submit_form" && event.details?.form_type === "final_timings"
          ? "Final Wedding Timings submitted" : activityLabel(event.action),
        detail: activityDetail(event.details),
      }));
    const events = [...emailEvents, ...noteEvents, ...auditEvents]
      .sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));
    const legacy = (r.legacy_timeline || []).map(event => `<div class="v811-timeline-event legacy"><i></i><span><strong>${esc(baseStatusTextV811(event.title || event.type || event.event || "Studio Ninja activity"))}</strong><small>${esc(event.date || event.at || event.occurred_at || "Date retained in the original record")}${event.detail ? ` · ${esc(event.detail)}` : ""}</small></span></div>`).join("");
    body.innerHTML = `<form id="note-form" class="composer v811-note-composer"><textarea id="note-body" rows="3" placeholder="Add a private note…" required></textarea><button class="primary" type="submit">Add note</button></form>
      <section class="v811-activity-heading"><div><small>COMPLETE CLIENT HISTORY</small><h3>Activity timeline</h3><p>Emails show their real sent or failed result, alongside payments, forms, agreements, notes and changes.</p></div><b>${events.length}</b></section>
      <div class="v811-timeline">${events.map(event => `<div class="v811-timeline-event ${event.type}" ${event.noteId ? `data-note="${attr(event.noteId)}"` : ""}><i>${event.type === "sent" ? "✓" : event.type === "failed" ? "!" : event.type === "note" ? "✎" : ""}</i><span><strong>${esc(event.label)}</strong><small>${esc(fmtDateTime(event.at))}${event.detail ? ` · ${esc(event.detail)}` : ""}</small></span>${event.retryEmailId && !event.retryContractCompletion ? `<button class="mini v817-retry-email" data-retry-email="${attr(event.retryEmailId)}" type="button">Retry email</button>` : ""}${event.retryContractCompletion ? `<button class="mini v817-retry-email" data-retry-contract-email type="button">Retry email</button>` : ""}${event.noteId ? `<button class="mini danger-text" data-delete-note type="button">Delete</button>` : ""}</div>`).join("") || `<div class="empty"><strong>No activity recorded yet</strong>The history will build automatically as this booking progresses.</div>`}</div>
      ${legacy ? `<h3 class="section-title">Imported Studio Ninja timeline</h3><div class="v811-timeline">${legacy}</div>` : ""}`;
    $("#note-form", body).onsubmit = async event => {
      event.preventDefault();
      await api(`/api/bookings/${r.id}/notes`, { method: "POST", body: JSON.stringify({ body: value("#note-body").trim() }) });
      toast("Private note added");
      await refresh();
      openDrawer(r.id, "Activity");
    };
    $$('[data-delete-note]', body).forEach(button => button.onclick = async () => {
      if (!confirm("Delete this private note?")) return;
      await api(`/api/notes/${button.closest("[data-note]").dataset.note}`, { method: "DELETE" });
      toast("Private note deleted");
      await refresh();
      openDrawer(r.id, "Activity");
    });
    $$('[data-retry-contract-email]', body).forEach(button => button.onclick = async () => {
      if (!confirm(`Retry the signed-agreement confirmation email to ${r.client.email}?`)) return;
      button.disabled = true;
      button.textContent = "Sending…";
      try {
        await api(`/api/bookings/${r.id}/contract/completion-email`, { method: "POST" });
        toast("Signed-agreement confirmation emailed");
        await refresh();
        openDrawer(r.id, "Activity");
      } catch (error) {
        button.disabled = false;
        button.textContent = "Retry email";
        toast(error.message, "error");
      }
    });
    $$('[data-retry-email]', body).forEach(button => button.onclick = async () => {
      if (!confirm(`Retry this exact email to ${r.client.email}?`)) return;
      button.disabled = true;
      button.textContent = "Sending…";
      try {
        await api(`/api/communications/failures/email/${encodeURIComponent(button.dataset.retryEmail)}/retry`, {method:"POST"});
        toast("Email sent successfully");
        await refresh();
        openDrawer(r.id, "Activity");
      } catch (error) {
        button.disabled = false;
        button.textContent = "Retry email";
        toast(error.message, "error");
      }
    });
  }

  renderTab = async function (r, tab, target = null) {
    const body = target || $("#drawer-body");
    const selected = canonicalSection(tab);
    if (!body) return;
    if (selected === "Journey") await renderJourneyV811(r, body);
    else if (selected === "Activity") renderActivityV811(r, body);
    else await baseRenderTabV811(r, legacySection(selected), body);
  };

  selectRecordTab = async function (r, tab, scroll = false, options = {}) {
    const selected = canonicalSection(tab);
    state.currentTab = selected;
    $$('[data-tab]', $("#drawer")).forEach(button => button.classList.toggle("active", canonicalSection(button.dataset.tab) === selected));
    await renderTab(r, selected);
    if (!applyingRoute) {
      writeRoute(bookingUrl(r.id, selected), {
        replace: Boolean(options.replace),
        state: { returnUrl: history.state?.returnUrl || workspaceUrl(parentViewForRecord(r)), openedFromApp: true },
      });
    }
    if (scroll) setTimeout(() => $(".record-workspace-tabs")?.scrollIntoView({ behavior: "smooth", block: "start" }), 25);
  };

  function derivedJourneyStatus(r) {
    if (r.journey_stage?.label) return r.journey_stage.label;
    if (r.status === "cancelled") return "Cancelled";
    if (r.status === "completed") return "Completed";
    const facts = recordJourneyFacts(r, state.currentPortal || {});
    const agreementComplete = Boolean(facts.contract && (
      facts.contract.is_legacy_import || facts.contract.fully_signed || facts.contract.supplier_signed_at
    ));
    if (facts.bookingForm && agreementComplete) {
      const finalCall = (r.tasks || []).find(task => task.workflow_key === "wbm_final_details_call");
      return finalCall?.completed ? "Ready for wedding" : "Booking details complete";
    }
    if (facts.hasPayment) return "Secured";
    if (facts.quote) return "Quote accepted";
    if (facts.quoteSent || r.status === "quoted") return "Quote sent";
    return r.kind === "wedding" ? "New enquiry" : statusText(r.status);
  }

  function suggestedAction(r) {
    const next = recordNextAction(r, state.currentPortal || {});
    if (next.action) return next;
    const title = next.title.toLowerCase();
    if (title.includes("send the package quote")) return { ...next, action: "send_quote" };
    if (title.includes("record their first payment") || title.includes("outstanding") || title.includes("balance remaining")) return { ...next, action: "record_payment" };
    if (title.includes("countersign")) return { ...next, action: "countersign" };
    if (title.includes("booking form") || title.includes("contract") || title.includes("agreement")) return { ...next, action: "review_forms" };
    if (title.includes("finalise")) return { ...next, action: "open_final_call_pack" };
    if (title.includes("to do")) return { ...next, action: "open_task" };
    return { ...next, action: "view" };
  }

  async function performRecordAction(r, section, action, details = {}) {
    await selectRecordTab(r, section, true);
    if (action === "send_quote") $("#send-quote")?.click();
    else if (action === "record_payment") ($("[data-payment-invoice]") || $("#new-invoice"))?.click();
    else if (action === "countersign") {
      const countersign = $("[data-countersign-contract]");
      if (countersign) countersign.click();
      else $(".v811-journey-forms")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    else if (action === "review_forms") $(".v811-journey-forms")?.scrollIntoView({ behavior: "smooth", block: "start" });
    else if (action === "review_booking_form") $(".v811-journey-forms")?.scrollIntoView({ behavior: "smooth", block: "start" });
    else if (action === "review_final_timings") $(".v820-final")?.scrollIntoView({ behavior: "smooth", block: "start" });
    else if (action === "retry_email") {
      const retry = details.emailId
        ? $(`[data-retry-email="${CSS.escape(details.emailId)}"]`, $("#drawer"))
        : $("[data-retry-email]", $("#drawer"));
      retry?.scrollIntoView({ behavior: "smooth", block: "center" });
      retry?.focus();
    }
    else if (action === "open_final_call_pack") $(".v823-final-call-pack")?.scrollIntoView({ behavior: "smooth", block: "start" });
    else if (action === "open_task") $(".overview-task-panel")?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function decorateOpenRecord(r) {
    const badge = $(".record-title-line .status", $("#drawer"));
    if (badge) {
      badge.textContent = derivedJourneyStatus(r);
      badge.className = `status ${recordStageClass(r)}`;
      const identity = badge.closest(".record-title-line")?.parentElement;
      identity?.querySelector(".v828-stage-help")?.remove();
      if (recordStage(r).help) badge.closest(".record-title-line")?.insertAdjacentHTML(
        "afterend", `<small class="v828-stage-help">${esc(recordStage(r).help)}</small>`
      );
    }
    const action = suggestedAction(r);
    const button = $("#next-record-action", $("#drawer"));
    if (button) button.onclick = () => performRecordAction(r, canonicalSection(action.tab), action.action, action);
  }

  openDrawer = async function (id, tab = "Overview", options = {}) {
    const selected = canonicalSection(tab);
    if (!applyingRoute) {
      writeRoute(bookingUrl(id, selected), {
        state: { returnUrl: workspaceUrl(state.view), openedFromApp: true },
      });
    }
    await baseOpenDrawerV811(id, legacySection(selected));
    if (state.current) {
      await selectRecordTab(state.current, selected, false, { replace: true });
      decorateOpenRecord(state.current);
      if (options.action) await performRecordAction(state.current, selected, options.action);
    }
  };

  closeDrawer = function () {
    const returnUrl = history.state?.returnUrl || workspaceUrl(parentViewForRecord(state.current));
    baseCloseDrawerV811();
    if (!applyingRoute && location.pathname.startsWith("/bookings/")) {
      writeRoute(returnUrl, { replace: true, state: { scrollY: history.state?.scrollY || 0 } });
    }
  };

  function queueItem(row) {
    const due = row.due_date ? ` · ${fmtDate(row.due_date)}` : "";
    const amount = row.amount !== null && row.amount !== undefined ? ` · ${money(row.amount)}` : "";
    const received = row.occurred_at ? ` · ${fmtDateTime(row.occurred_at)}` : "";
    const mailData = row.action === "open_email" ? ` data-mail-brand="${attr(row.mail_brand)}" data-mail-uid="${attr(row.mail_uid)}"` : "";
    const failureData = row.failure_id ? ` data-failure-kind="${attr(row.failure_kind)}" data-failure-id="${attr(row.failure_id)}"` : "";
    const ownerData = row.private_owner_notification ? ` data-private-owner="1"` : "";
    const openLabel = row.action === "open_email" ? "Read email" : row.action === "retry_communication" ? "Retry now" : row.update_type ? "Review" : "Open";
    return `<button class="v811-queue-item" data-queue-record="${attr(row.booking_id)}" data-section="${attr(row.section)}" data-action="${attr(row.action)}"${mailData}${failureData}${ownerData}><span class="record-avatar ${row.brand}">${esc(row.title.split(/\s+|&/).filter(Boolean).slice(0, 2).map(word => word[0]).join(""))}</span><span><strong>${esc(row.title)}</strong><small>${esc(row.detail)}${esc(received)}${esc(due)}${esc(amount)}</small></span><b>${openLabel} →</b></button>`;
  }

  function queueCard(key, rows) {
    const [label, help, icon] = queueCopy[key];
    const paymentTotal = key === "payments_due"
      ? rows.reduce((sum, row) => sum + Number(row.amount || 0), 0)
      : null;
    const total = paymentTotal !== null
      ? `<b class="v819-payment-total">${money(paymentTotal)} total due</b>`
      : "";
    return `<button data-queue-jump="${key}" class="${rows.length ? "has-items" : ""}"><i>${icon}</i><span><strong>${rows.length}</strong><small>${label}</small>${total}<em>${help}</em></span></button>`;
  }

  function renderTodayDashboard(data, renderNumber) {
    if (renderNumber !== dashboardRenderNumber || state.view !== "dashboard") return;
    const d = state.dashboard || {};
    const queues = Object.fromEntries(queueOrder.map(key => [key, (data.queues[key] || []).filter(row => state.brand === "all" || row.brand === state.brand)]));
    const actionBookingIds = new Set(actionQueueOrder.flatMap(key => queues[key].map(row => row.booking_id)));
    const urgent = actionBookingIds.size;
    const upcomingSource = state.brand === "ivory"
      ? (d.upcoming || []).filter(record => record.kind === "digital")
      : (d.upcoming_weddings || d.upcoming || []);
    const upcoming = filtered(upcomingSource);
    const upcomingTitle = state.brand === "ivory" ? "Upcoming projects" : "Upcoming weddings";
    const upcomingHelp = state.brand === "ivory"
      ? "Your next project dates and deadlines"
      : "Your next wedding dates, in order";
    const tasks = (d.tasks || []).filter(task => state.brand === "all" || state.records.find(record => record.id === task.booking_id)?.brand === state.brand);
    const actionKeys = actionQueueOrder.filter(key => queues[key].length);
    const waitingKeys = waitingQueueOrder.filter(key => queues[key].length);
    $("#content").innerHTML = `<section class="v811-today-head"><div><small>YOUR WORKING DAY</small><h2>Today</h2><p>Action items are separated from clients you are simply waiting for.</p></div><b class="${urgent ? "attention" : "clear"}">${urgent ? `${urgent} client${urgent === 1 ? "" : "s"} need action` : "All clear"}</b></section>
      <section class="panel v824-upcoming-weddings"><div class="panel-title"><div><h2>${esc(upcomingTitle)}</h2><p>${esc(upcomingHelp)}</p></div><button data-jump="calendar">View all</button></div>${upcoming.length ? upcoming.slice(0, 7).map(recordRow).join("") : `<div class="empty"><strong>No upcoming records</strong>Your next dated booking will appear here.</div>`}</section>
      <section class="v828-dashboard-group action"><header><div><small>START HERE</small><h2>Needs your action</h2><p>Only clients with something you can genuinely do now.</p></div><b>${urgent}</b></header><div class="v811-queue-cards">${actionQueueOrder.map(key => queueCard(key, queues[key])).join("")}</div><div class="v811-worklists">${actionKeys.map(key => `<article id="queue-${key}" class="panel v811-queue-panel"><div class="panel-title"><div><h2>${esc(queueCopy[key][0])}</h2><p>${esc(queueCopy[key][1])}</p></div><b>${queues[key].length}</b></div>${queues[key].map(queueItem).join("")}</article>`).join("") || `<article class="panel empty"><strong>Nothing needs immediate attention</strong>You are clear to move on to the waiting and upcoming list.</article>`}</div></section>
      <section class="v828-dashboard-group waiting"><header><div><small>KEEP AN EYE ON</small><h2>Waiting and upcoming</h2><p>No action is needed until the couple responds or a payment becomes due.</p></div><b>${waitingKeys.reduce((sum, key) => sum + queues[key].length, 0)}</b></header><div class="v811-queue-cards">${waitingQueueOrder.map(key => queueCard(key, queues[key])).join("")}</div><div class="v811-worklists">${waitingKeys.map(key => `<article id="queue-${key}" class="panel v811-queue-panel"><div class="panel-title"><div><h2>${esc(queueCopy[key][0])}</h2><p>${esc(queueCopy[key][1])}</p></div><b>${queues[key].length}</b></div>${queues[key].map(queueItem).join("")}</article>`).join("") || `<article class="panel empty"><strong>Nothing is waiting</strong>There are no watched client steps or payments in the next 60 days.</article>`}</div></section>
      <section class="dash-grid v811-dashboard-lower v824-dashboard-tasks"><article class="panel"><div class="panel-title"><div><h2>Private things to do · ${d.open_tasks || 0}</h2><p>These never email a client</p></div><button data-jump="workflows">View all</button></div>${tasks.length ? tasks.slice(0, 7).map(task => taskRow(task, true)).join("") : `<div class="empty"><strong>You're all caught up</strong>No open private tasks.</div>`}</article></section>`;
    $$('[data-queue-record]', $("#content")).forEach(button => button.onclick = () => {
      if (button.dataset.action === "open_email" && window.openInboxMessageFromDashboard) {
        window.openInboxMessageFromDashboard(button.dataset.mailBrand, button.dataset.mailUid);
      } else if (button.dataset.action === "retry_communication") {
        const ownerNotification = button.dataset.privateOwner === "1";
        if (!confirm(ownerNotification ? "Retry this private notification to Mark now?" : "Retry this client email now?")) return;
        button.disabled = true;
        button.querySelector("b").textContent = "Retrying…";
        api(`/api/communications/failures/${encodeURIComponent(button.dataset.failureKind)}/${encodeURIComponent(button.dataset.failureId)}/retry`, {method:"POST"})
          .then(async()=>{workflowQueueCache=null;toast(ownerNotification ? "Private notification sent successfully" : "Email sent successfully");await refresh();renderDashboard()})
          .catch(error=>{button.disabled=false;button.querySelector("b").textContent="Retry now →";toast(error.message,"error")});
      } else {
        openDrawer(button.dataset.queueRecord, button.dataset.section, { action: button.dataset.action });
      }
    });
    $$('[data-queue-jump]', $("#content")).forEach(button => button.onclick = () => $(`#queue-${button.dataset.queueJump}`)?.scrollIntoView({ behavior: "smooth", block: "start" }));
    wireRecords();
    $$('[data-action="toggle-task"]', $("#content")).forEach(button => button.onclick = () => toggleTask(button.closest("[data-task]")));
  }

  renderDashboard = function () {
    const renderNumber = ++dashboardRenderNumber;
    $("#content").innerHTML = `<div class="panel loading">Building today's working queues…</div>`;
    const workflowRequest = workflowQueueCache ? Promise.resolve(workflowQueueCache) : api("/api/workflow-queues").then(data => (workflowQueueCache = data));
    const mailRequest = api("/api/mail/messages?unread_only=true&limit=30").catch(() => ({ messages: [] }));
    Promise.all([workflowRequest, mailRequest]).then(([data, mail]) => {
      const emailUpdates = (mail.messages || []).filter(message => message.unread && message.booking).map(message => ({
        booking_id: message.booking.id,
        title: message.booking.title,
        detail: `Email reply · ${message.subject || "No subject"} · ${message.from_email}`,
        section: "Activity",
        action: "open_email",
        brand: message.booking.brand,
        event_date: message.booking.event_date,
        due_date: null,
        amount: null,
        occurred_at: message.date,
        update_type: "email_reply",
        mail_brand: message.brand,
        mail_uid: message.uid,
      }));
      const merged = {...data, queues: {...data.queues, client_updates: [...(data.queues.client_updates || []), ...emailUpdates].sort((a,b) => String(b.occurred_at || "").localeCompare(String(a.occurred_at || "")))}};
      renderTodayDashboard(merged, renderNumber);
    }).catch(error => showError(error));
  };

  async function loadSearchIndex() {
    if (searchIndexCache) return searchIndexCache;
    const [activeRecords, archivedRecords, activeInvoices, archivedInvoices] = await Promise.all([
      api("/api/bookings"), api("/api/bookings?archived=true"),
      api("/api/invoices"), api("/api/invoices?archived=true"),
    ]);
    const records = [...activeRecords, ...archivedRecords].filter((record, index, rows) => rows.findIndex(item => item.id === record.id) === index);
    searchIndexCache = { records, invoices: [...activeInvoices, ...archivedInvoices] };
    return searchIndexCache;
  }

  function searchResultRecord(record, recent = false) {
    return `<button class="v811-search-result" data-search-record="${attr(record.id)}" data-section="Overview"><i class="record-avatar ${record.brand}">${esc(initials(record))}</i><span><strong>${esc(record.title)}</strong><small>${esc(record.venue_or_project || record.client.email)}${record.archived ? " · Archived" : ""}</small></span><em>${recent ? "Recent" : recordStageLabel(record)}</em></button>`;
  }

  async function showGlobalSearch(query = "") {
    const panel = $("#global-search-results");
    if (!panel) return;
    panel.classList.remove("hidden");
    panel.innerHTML = `<div class="v811-search-loading">Searching all clients and invoices…</div>`;
    try {
      const index = await loadSearchIndex();
      const term = query.trim().toLowerCase();
      let records;
      let invoices = [];
      if (!term) {
        records = [...index.records].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at))).slice(0, 6);
      } else {
        records = index.records.filter(record => `${record.title} ${record.client.email} ${record.client.phone || ""} ${record.venue_or_project || ""} ${record.package_name || ""}`.toLowerCase().includes(term)).slice(0, 8);
        invoices = index.invoices.filter(invoice => `${invoice.number} ${invoice.legacy_number || ""} ${invoice.client || ""}`.toLowerCase().includes(term)).slice(0, 6);
      }
      panel.innerHTML = `<header><strong>${term ? "Search results" : "Recently updated clients"}</strong><small>${records.length + invoices.length} found</small></header>${records.map(record => searchResultRecord(record, !term)).join("")}${invoices.map(invoice => `<button class="v811-search-result invoice" data-search-record="${attr(invoice.booking_id)}" data-section="Payments"><i>£</i><span><strong>${esc(invoice.number)} · ${esc(invoice.client || "Client")}</strong><small>${esc(statusText(invoice.status))} · ${money(invoice.balance)} remaining</small></span><em>Invoice</em></button>`).join("")}${records.length + invoices.length ? "" : `<div class="empty"><strong>No matching client or invoice</strong>Try a name, email, venue or invoice number.</div>`}`;
      $$('[data-search-record]', panel).forEach(button => button.onclick = () => {
        panel.classList.add("hidden");
        openDrawer(button.dataset.searchRecord, button.dataset.section);
      });
    } catch (error) {
      panel.innerHTML = `<div class="empty"><strong>Search is unavailable</strong>${esc(error.message)}</div>`;
    }
  }

  function bindV811() {
    const searchHost = $(".topbar .search");
    if (searchHost && !$("#global-search-results")) {
      searchHost.classList.add("v811-global-search");
      searchHost.insertAdjacentHTML("beforeend", `<section id="global-search-results" class="v811-search-results hidden"></section>`);
    }
    const search = $("#search");
    search.oninput = event => {
      state.search = event.target.value.toLowerCase();
      render();
      if (!location.pathname.startsWith("/bookings/")) writeRoute(workspaceUrl(state.view), { replace: true });
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => showGlobalSearch(state.search), 120);
    };
    search.onfocus = () => showGlobalSearch(state.search);
    document.addEventListener("pointerdown", event => {
      if (!event.target.closest(".v811-global-search")) $("#global-search-results")?.classList.add("hidden");
    });
    document.addEventListener("click", event => {
      if (event.target.closest("[data-status], #archive-toggle")) setTimeout(() => {
        if (!location.pathname.startsWith("/bookings/")) writeRoute(workspaceUrl(state.view), { replace: true });
      }, 0);
    });
    $$("#brand-menu button").forEach(button => button.addEventListener("click", () => {
      if (!location.pathname.startsWith("/bookings/")) writeRoute(workspaceUrl(state.view), { replace: true });
      workflowQueueCache = null;
    }));
    $("#drawer-overlay").onclick = closeDrawer;
    window.addEventListener("popstate", () => applyCurrentRoute());
  }

  window.WBMRouter = { applyCurrentRoute };
  bindV811();
  setTimeout(() => {
    if (!initialRouteApplied && !$("#app")?.classList.contains("hidden") && state.records.length) {
      applyCurrentRoute({ replace: true });
    }
  }, 250);
})();
