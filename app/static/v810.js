(() => {
  const baseRenderSettingsV810 = renderSettings;

  function statusCard(data) {
    const enabled = Boolean(data.enabled);
    return `<section class="panel accounts-integration-card">
      <header><div><small>ONE-WAY, SAFE ACCOUNTING LINK</small><h2>Accounts 2026 integration</h2><p>Wedding invoices remain controlled here and are mirrored without renumbering.</p></div><span class="integration-state ${enabled ? "live" : ""}">${enabled ? (data.auto_sync ? "LIVE + AUTOMATIC" : "LIVE · MANUAL FIRST SYNC") : "DISABLED IN YAML"}</span></header>
      <div class="integration-counts"><div><strong>${Number(data.eligible || 0)}</strong><span>ELIGIBLE WEDDING INVOICES</span></div><div><strong>${Number(data.synced || 0)}</strong><span>UP TO DATE</span></div><div><strong>${Number(data.pending || 0)}</strong><span>WAITING TO SYNC</span></div><div><strong>${Number(data.errors || 0)}</strong><span>NEED ATTENTION</span></div></div>
      <div class="integration-explainer"><strong>Protected scope:</strong> Weddings By Mark wedding jobs from 6 April 2025 onwards, plus older weddings only where a payment falls inside that accounting period. Test records, enquiries and Ivory Digital projects are excluded. No client emails are sent.</div>
      <div class="integration-actions"><button id="accounts-check" class="secondary" type="button" ${enabled ? "" : "disabled"}>Check connection</button><button id="accounts-sync" class="primary" type="button" ${enabled && data.pending ? "" : "disabled"}>Sync ${Number(data.pending || 0)} waiting</button></div>
      <small class="integration-foot">Last successful sync: ${data.last_synced_at ? esc(fmtDate(data.last_synced_at)) : "Not run yet"} · Original invoice numbers and signed payment entries are preserved.</small>
    </section>`;
  }

  async function loadIntegrationCard() {
    const grid = document.querySelector(".settings-grid");
    if (!grid) return;
    try {
      const data = await api("/api/accounts-integration/status");
      grid.insertAdjacentHTML("afterbegin", statusCard(data));
      document.querySelector("#accounts-check")?.addEventListener("click", async () => {
        try {
          await api("/api/accounts-integration/connection");
          toast("Accounts 2026 connection is secure and ready");
        } catch (error) { toast(error.message, "error"); }
      });
      document.querySelector("#accounts-sync")?.addEventListener("click", () => {
        showModal("Start the protected accounts sync", `<div class="full integration-explainer"><strong>${Number(data.pending || 0)} invoice revision${Number(data.pending || 0) === 1 ? "" : "s"} waiting</strong><br>Nothing in the booking system will be changed. No emails, reminders or client links will be created.</div><label class="full">Type SYNC ELIGIBLE WEDDING INVOICES<input id="accounts-sync-confirm" autocomplete="off" required></label>`, async () => {
          const result = await api("/api/accounts-integration/sync", {method:"POST", body:JSON.stringify({confirmation:value("#accounts-sync-confirm").trim()})});
          closeModal();
          toast(`${result.synced} invoice${result.synced === 1 ? "" : "s"} safely synchronised`);
          renderSettings();
        }, "This is idempotent: running it again cannot duplicate or renumber an invoice.");
      });
    } catch (error) {
      grid.insertAdjacentHTML("afterbegin", `<section class="panel accounts-integration-card"><h2>Accounts 2026 integration</h2><p class="error">${esc(error.message)}</p></section>`);
    }
  }

  renderSettings = function () {
    baseRenderSettingsV810();
    loadIntegrationCard();
  };
})();
