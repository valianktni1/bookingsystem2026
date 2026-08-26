/* V8.30.1 - dedicated Studio-inspired mobile dashboard, wedding list and client workspace. */
(() => {
  "use strict";

  const mobileWorkspace = () => window.matchMedia("(max-width: 760px)").matches;
  const baseRecordSectionNavigationV8301 = recordSectionNavigation;
  const baseSelectRecordTabV8301 = selectRecordTab;

  function mobileSectionsV8301(record, portal) {
    const submissions = portal?.submissions || [];
    const invoices = (record.invoices || []).filter(invoice => !["void", "cancelled"].includes(invoice.status));
    const balance = invoices.reduce((sum, invoice) => sum + Number(invoice.balance || 0), 0);
    const contract = portal?.contract;
    const signed = Boolean(contract && (contract.is_legacy_import || contract.fully_signed || contract.supplier_signed_at));
    const openTasks = (record.tasks || []).filter(task => !task.completed).length;
    return [
      {tab: "Overview", icon: "♙", label: "Couple & wedding", help: `${record.venue_or_project || "Venue not set"} · ${fmtDate(record.event_date)}`},
      {tab: "Quote", icon: "✉", label: "Quote & mail", help: portal?.quote ? "Quote accepted · open email controls" : "Quote, client area and email conversation"},
      {tab: "Payments", icon: "£", label: "Invoices & payments", help: balance > 0 ? `${money(balance)} outstanding` : `${invoices.length} invoice${invoices.length === 1 ? "" : "s"} · account clear`},
      {tab: "Forms", icon: "✓", label: "Agreement & forms", help: `${submissions.length} submitted · agreement ${signed ? "complete" : "waiting"}`},
      {tab: "Files", icon: "▤", label: "Files", help: `${(record.documents || []).length} retained document${(record.documents || []).length === 1 ? "" : "s"}`},
      {tab: "Notes", icon: "✎", label: "Notes & activity", help: `${openTasks} open private task${openTasks === 1 ? "" : "s"} · complete history`},
    ];
  }

  recordSectionNavigation = function (selected) {
    if (!mobileWorkspace()) return baseRecordSectionNavigationV8301(selected);
    const record = state.current;
    return `<section class="v8301-mobile-sections" aria-label="Booking sections">
      ${mobileSectionsV8301(record, state.currentPortal).map(section => `<article class="v8301-mobile-section ${section.tab === selected ? "open" : ""}" data-mobile-section="${section.tab}">
        <button data-tab="${section.tab}" type="button" aria-expanded="${section.tab === selected}"><i>${section.icon}</i><span><strong>${section.label}</strong><small>${esc(section.help)}</small></span><b>⌄</b></button>
        <div class="drawer-body v8301-mobile-section-body ${section.tab === selected ? "" : "hidden"}" data-section-body="${section.tab}"></div>
      </article>`).join("")}
    </section>`;
  };

  selectRecordTab = function (record, tab, scroll = false) {
    if (!mobileWorkspace() || !$(`[data-section-body]`, $("#drawer"))) {
      return baseSelectRecordTabV8301(record, tab, scroll);
    }
    const selected = normaliseRecordTab(tab);
    const drawer = $("#drawer");
    state.currentTab = selected;
    $$('[data-tab]', drawer).forEach(button => {
      const open = button.dataset.tab === selected;
      button.classList.toggle("active", open);
      button.setAttribute("aria-expanded", String(open));
      button.closest("[data-mobile-section]")?.classList.toggle("open", open);
    });
    const body = $(`[data-section-body="${selected}"]`, drawer);
    $$('[data-section-body]', drawer).forEach(sectionBody => sectionBody.classList.toggle("hidden", sectionBody !== body));
    if (!body) return baseSelectRecordTabV8301(record, selected, scroll);
    renderTab(record, selected, body);
    if (scroll) setTimeout(() => body.closest("[data-mobile-section]")?.scrollIntoView({behavior: "smooth", block: "start"}), 35);
  };

  function mobileDashboardShortcutsV8301() {
    if (!mobileWorkspace() || state.view !== "dashboard") return;
    const content = $("#content");
    if (!content || content.querySelector(".v8301-mobile-shortcuts") || content.querySelector(".loading")) return;
    content.insertAdjacentHTML("afterbegin", `<nav class="v8301-mobile-shortcuts" aria-label="Quick access">
      <button data-mobile-jump="enquiries" type="button"><i>◎</i><span>Enquiries</span></button>
      <button data-mobile-jump="weddings" type="button"><i>♡</i><span>Weddings</span></button>
      <button data-mobile-jump="calendar" type="button"><i>□</i><span>Calendar</span></button>
      <button data-mobile-jump="invoices" type="button"><i>£</i><span>Payments</span></button>
      <button data-mobile-jump="mail" type="button"><i>✉</i><span>Inbox</span></button>
      <button data-mobile-jump="settings" type="button"><i>⚙</i><span>Settings</span></button>
    </nav>`);
    $$('[data-mobile-jump]', content).forEach(button => button.onclick = () => navigate(button.dataset.mobileJump));
  }

  const content = $("#content");
  if (content) new MutationObserver(mobileDashboardShortcutsV8301).observe(content, {childList: true});
  window.addEventListener("resize", mobileDashboardShortcutsV8301);
})();
