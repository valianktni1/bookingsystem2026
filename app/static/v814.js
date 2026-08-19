/* V8.14 - one-click complete business-data backup. */
(() => {
  "use strict";

  const baseRenderSettingsV814 = renderSettings;

  function wireBackupDownload() {
    const button = document.querySelector("#complete-backup-download");
    if (!button) return;
    button.addEventListener("click", () => {
      const original = button.innerHTML;
      button.classList.add("preparing");
      button.innerHTML = "<span>↓</span> Preparing your backup…";
      toast("Preparing the complete backup. Your download will start shortly.");
      window.setTimeout(() => {
        if (!document.body.contains(button)) return;
        button.classList.remove("preparing");
        button.innerHTML = original;
      }, 7000);
    });
  }

  renderSettings = function () {
    baseRenderSettingsV814();
    const content = document.querySelector("#content");
    if (!content) return;
    content.insertAdjacentHTML("afterbegin", `<section class="panel v814-backup-card">
      <div class="v814-backup-copy">
        <span class="v814-backup-icon">↧</span>
        <div><small>PRIVATE COMPLETE BACKUP</small><h2>Download everything safely</h2>
        <p>Creates one dated ZIP containing every booking, client, invoice, payment, form, agreement, note, task, audit record and uploaded document.</p></div>
      </div>
      <div class="v814-backup-includes">
        <span>✓ Complete database snapshot</span><span>✓ Uploaded client files</span>
        <span>✓ Invoices, receipts and CSVs</span><span>✓ Running program source</span>
      </div>
      <div class="v814-backup-security"><strong>Store the download somewhere private.</strong><span>It contains confidential client and financial information. Passwords, Google and email credentials are deliberately excluded.</span></div>
      <footer>
        <a id="complete-backup-download" class="primary v814-backup-button" href="/api/backups/complete" download><span>↓</span> Download complete backup</a>
        <small>Read-only: this does not email clients, change bookings, alter invoices or touch Google Calendar.</small>
      </footer>
    </section>`);
    wireBackupDownload();
  };
})();
