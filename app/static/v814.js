/* V8.23.1 - reliable background preparation and resumable backup delivery. */
(() => {
  "use strict";

  const baseRenderSettingsV814 = renderSettings;
  const wait = milliseconds => new Promise(resolve => window.setTimeout(resolve, milliseconds));

  function wireBackupDownload() {
    const button = document.querySelector("#complete-backup-download");
    const statusBox = document.querySelector("#complete-backup-status");
    const statusText = document.querySelector("#complete-backup-status-text");
    const statusPercent = document.querySelector("#complete-backup-status-percent");
    const statusProgress = document.querySelector("#complete-backup-progress");
    if (!button) return;

    function showStatus(job, failed = false) {
      if (!statusBox) return;
      const progress = Math.max(0, Math.min(100, Number(job?.progress || 0)));
      statusBox.classList.remove("hidden", "failed", "ready");
      statusBox.classList.toggle("failed", failed || job?.status === "failed");
      statusBox.classList.toggle("ready", job?.status === "ready");
      statusText.textContent = job?.message || "Preparing your complete backup";
      statusPercent.textContent = `${progress}%`;
      statusProgress.value = progress;
    }

    async function prepareAndDownload() {
      button.classList.add("preparing");
      button.disabled = true;
      button.innerHTML = "<span>↓</span> Preparing your backup…";
      showStatus({progress: 0, message: "Starting the complete private backup"});
      toast("Your backup is preparing safely in the background.");
      try {
        let job = await api("/api/backups/complete", {method: "POST"});
        showStatus(job);
        for (let attempt = 0; attempt < 1200 && job.status !== "ready"; attempt += 1) {
          if (job.status === "failed") throw new Error(job.message || "The backup could not be prepared");
          await wait(1500);
          job = await api(`/api/backups/complete/${encodeURIComponent(job.job_id)}`);
          showStatus(job);
        }
        if (job.status !== "ready" || !job.download_url) {
          throw new Error("The backup took too long to prepare. Please press the button to try again.");
        }
        const link = document.createElement("a");
        link.href = job.download_url;
        link.download = job.filename || "BookingSystem2026-complete-backup.zip";
        link.hidden = true;
        document.body.appendChild(link);
        link.click();
        link.remove();
        button.innerHTML = "<span>✓</span> Backup download started";
        toast(`Complete backup ready${job.size_bytes ? ` (${bytes(job.size_bytes)})` : ""}.`);
      } catch (error) {
        showStatus({status: "failed", progress: 0,
          message: error.message || "The backup could not be prepared"}, true);
        toast(error.message || "The backup could not be prepared", "error");
        button.innerHTML = "<span>↻</span> Try complete backup again";
      } finally {
        button.disabled = false;
        button.classList.remove("preparing");
      }
    }

    button.addEventListener("click", prepareAndDownload);
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
        <button type="button" id="complete-backup-download" class="primary v814-backup-button"><span>↓</span> Download complete backup</button>
        <small>Read-only: this does not email clients, change bookings, alter invoices or touch Google Calendar.</small>
      </footer>
      <div id="complete-backup-status" class="v814-backup-status hidden" role="status" aria-live="polite">
        <div><span id="complete-backup-status-text">Preparing your complete backup</span><strong id="complete-backup-status-percent">0%</strong></div>
        <progress id="complete-backup-progress" max="100" value="0">0%</progress>
        <small>It is safe to keep using the booking system while this finishes. The download starts only after the ZIP is ready.</small>
      </div>
    </section>`);
    wireBackupDownload();
  };
})();
