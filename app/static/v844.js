/* V8.44 - one authoritative booking-workspace navigation controller. */
(() => {
  "use strict";

  // Keep the proven composite renderer for the two sections whose content is
  // deliberately assembled by several specialist features (final timings,
  // final-call pack and the combined activity history). All other sections
  // are dispatched directly so an older compatibility layer cannot silently
  // turn one selected tab into another screen.
  const compositeRenderTabV844 = renderTab;
  let renderRevisionV844 = 0;

  const sectionSlugsV844 = {
    Overview: "overview",
    Journey: "journey",
    Emails: "emails",
    Payments: "payments",
    Files: "files",
    Activity: "activity",
  };

  function canonicalSectionV844(tab) {
    return ({
      Overview: "Overview",
      Workflow: "Overview",
      Quote: "Journey",
      Journey: "Journey",
      Forms: "Journey",
      Questionnaires: "Journey",
      "Client portal": "Journey",
      Email: "Emails",
      Mail: "Emails",
      Emails: "Emails",
      Finance: "Payments",
      Payments: "Payments",
      Documents: "Files",
      Files: "Files",
      Notes: "Activity",
      "Notes & activity": "Activity",
      Activity: "Activity",
    })[tab] || "Overview";
  }

  function sectionRowsV844(record, portal) {
    const invoices = (record?.invoices || []).filter(invoice => !["void", "cancelled"].includes(invoice.status));
    const outstanding = invoices.reduce((total, invoice) => total + Number(invoice.balance || 0), 0);
    const submissions = portal?.submissions || [];
    const contract = portal?.contract;
    const agreementComplete = Boolean(contract && (
      contract.is_legacy_import || contract.fully_signed || contract.supplier_signed_at
    ));
    const journeyComplete = Number(Boolean(portal?.quote))
      + Number(Boolean(submissions.find(item => item.form_type === "booking_form")))
      + Number(agreementComplete);
    const openTasks = (record?.tasks || []).filter(task => !task.completed).length;
    return [
      {tab: "Overview", icon: "⌂", label: "Overview", meta: `${openTasks} to do`},
      {tab: "Journey", icon: "✓", label: "Journey", meta: `${journeyComplete}/3 complete`},
      {tab: "Emails", icon: "✉", label: "Emails", meta: `${(portal?.emails || []).length} recorded`},
      {tab: "Payments", icon: "£", label: "Payments", meta: outstanding > 0 ? `${money(outstanding)} due` : "Clear"},
      {tab: "Files", icon: "▤", label: "Files", meta: `${(record?.documents || []).length} retained`},
      {tab: "Activity", icon: "◷", label: "Activity", meta: `${(record?.activity || []).length} events`},
    ];
  }

  normaliseRecordTab = canonicalSectionV844;

  recordSectionNavigation = function (selected) {
    const active = canonicalSectionV844(selected);
    const rows = sectionRowsV844(state.current, state.currentPortal);
    return `<section class="v844-workspace-shell">
      <nav class="record-workspace-tabs v844-tabs" aria-label="Booking workspace">
        ${rows.map(row => `<button type="button" class="${row.tab === active ? "active" : ""}" data-tab="${row.tab}" aria-current="${row.tab === active ? "page" : "false"}"><i>${row.icon}</i><span><strong>${row.label}</strong><small>${esc(row.meta)}</small></span></button>`).join("")}
      </nav>
      <div id="drawer-body" class="drawer-body record-workspace-body v844-workspace-body" data-v844-section="${active}"></div>
    </section>`;
  };

  function bookingRouteV844(record, section) {
    const url = new URL(location.href);
    url.pathname = `/bookings/${encodeURIComponent(record.id)}/${sectionSlugsV844[section]}`;
    if (state.brand && state.brand !== "all") url.searchParams.set("brand", state.brand);
    else url.searchParams.delete("brand");
    return `${url.pathname}${url.search}`;
  }

  function syncBookingRouteV844(record, section) {
    if (!record || !history?.replaceState) return;
    const target = bookingRouteV844(record, section);
    const current = `${location.pathname}${location.search}`;
    const routeState = {...(history.state || {}), wbm: true};
    if (current === target) history.replaceState(routeState, "", target);
    else history.pushState(routeState, "", target);
  }

  renderTab = async function (record, tab, target = null) {
    const body = target || $("#drawer-body");
    const selected = canonicalSectionV844(tab);
    if (!body) return;
    const revision = ++renderRevisionV844;
    body.dataset.v844Section = selected;
    body.setAttribute("aria-busy", selected === "Journey" ? "true" : "false");
    try {
      if (selected === "Overview") renderOverview(record, body);
      else if (selected === "Journey") await compositeRenderTabV844(record, "Journey", body);
      else if (selected === "Emails") renderBookingEmails(record, body);
      else if (selected === "Payments") renderFinance(record, body);
      else if (selected === "Files") renderRecordDocuments(record, body);
      else if (selected === "Activity") await compositeRenderTabV844(record, "Activity", body);
    } catch (error) {
      if (revision !== renderRevisionV844) return;
      body.innerHTML = `<div class="v844-section-error"><strong>${esc(selected)} could not be displayed</strong><span>${esc(error.message || "Please try again.")}</span><button type="button" class="secondary" data-v844-retry>Try again</button></div>`;
      $("[data-v844-retry]", body).onclick = () => renderTab(record, selected, body);
      toast(`${selected} could not be displayed`, "error");
    } finally {
      if (revision === renderRevisionV844) body.setAttribute("aria-busy", "false");
    }
  };

  selectRecordTab = async function (record, tab, scroll = false) {
    const selected = canonicalSectionV844(tab);
    const drawer = $("#drawer");
    const body = $("#drawer-body", drawer);
    state.currentTab = selected;
    $$('[data-tab]', drawer).forEach(button => {
      const active = canonicalSectionV844(button.dataset.tab) === selected;
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
      button.setAttribute("aria-expanded", String(active));
    });
    syncBookingRouteV844(record, selected);
    await renderTab(record, selected, body);
    if (scroll) setTimeout(() => $(".v844-tabs", drawer)?.scrollIntoView({behavior: "smooth", block: "start"}), 25);
  };

  window.WBMWorkspaceV844 = Object.freeze({
    version: "8.44",
    canonicalSection: canonicalSectionV844,
    sections: Object.keys(sectionSlugsV844),
  });
})();
