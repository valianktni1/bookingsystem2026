/* V8.32 - genuinely friendly desktop/mobile workspace and direct job actions. */
(() => {
  "use strict";

  const baseOpenDrawerV832 = openDrawer;

  function quickAction(icon, label, action, extra = "") {
    return `<button type="button" data-v832-action="${action}" ${extra}><i>${icon}</i><span>${label}</span></button>`;
  }

  function decorateFriendlyWorkspace() {
    const drawer = $("#drawer");
    const record = state.current;
    const header = $(".record-command-header", drawer);
    if (!drawer || !record || !header || $(".v832-quick-actions", drawer)) return;

    header.insertAdjacentHTML("afterend", `<nav class="v832-quick-actions" aria-label="Most-used booking actions">
      ${quickAction("✉", "Email", "email")}
      ${record.client.phone ? quickAction("☎", "Call", "call") : quickAction("☎", "Call", "call", "disabled aria-disabled=\"true\"")}
      ${quickAction("£", "Invoice", "invoice")}
      ${quickAction("?", "Questionnaire", "forms")}
      ${quickAction("✎", "Notes", "notes")}
      ${quickAction("•••", "More", "more")}
    </nav>`);

    $$('[data-v832-action]', drawer).forEach(button => button.onclick = () => {
      const action = button.dataset.v832Action;
      if (action === "email") $("#record-email-client-top", drawer)?.click();
      else if (action === "call" && record.client.phone) location.href = `tel:${record.client.phone}`;
      else if (action === "invoice") selectRecordTab(record, "Payments", true);
      else if (action === "forms") selectRecordTab(record, "Forms", true);
      else if (action === "notes") selectRecordTab(record, "Notes", true);
      else if (action === "more") {
        drawer.scrollTo({top: 0, behavior: "smooth"});
        setTimeout(() => $("#record-more", drawer)?.click(), 120);
      }
    });
  }

  openDrawer = async function (id, tab = "Overview", options = {}) {
    await baseOpenDrawerV832(id, tab, options);
    decorateFriendlyWorkspace();
  };

  const drawer = $("#drawer");
  if (drawer) new MutationObserver(() => {
    if (!drawer.classList.contains("hidden")) decorateFriendlyWorkspace();
  }).observe(drawer, {childList: true, subtree: false});
})();
