/* V8.12 - direct Google Calendar connection and booking sync controls. */
(() => {
  "use strict";

  const baseRenderSettingsV812 = renderSettings;

  function calendarNotice() {
    const result = new URLSearchParams(location.search).get("google_calendar");
    return ({
      connected: ["Google Calendar connected", "The next accepted wedding will sync automatically. Use Sync current bookings once if you also want existing jobs added."],
      denied: ["Connection cancelled", "Nothing was changed."],
      invalid: ["Connection link expired", "Please press Connect Google Calendar again."],
      error: ["Google could not be connected", "Check the Google Cloud Client ID, secret and exact redirect address, then try again."],
    })[result] || null;
  }

  function renderCalendarCard(status) {
    const host = document.querySelector("#google-calendar-settings");
    if (!host) return;
    const ready = status.configured && status.connected;
    const counts = ready ? `<div class="v812-calendar-counts">
      <span><b>${status.synced}</b> synced</span><span><b>${status.pending}</b> pending</span><span class="${status.errors ? "attention" : ""}"><b>${status.errors}</b> errors</span>
    </div>` : "";
    const problems = ready && status.problems?.length ? `<div class="v812-calendar-problems"><strong>Bookings needing attention</strong>${status.problems.map(item => `<a href="/bookings/${encodeURIComponent(item.booking_id)}/overview"><span>${esc(item.title)}</span><small>${esc(item.error || item.status)}</small></a>`).join("")}</div>` : "";
    host.innerHTML = `<div class="v812-calendar-head">
      <span class="v812-calendar-icon">31</span>
      <div><small>GOOGLE CALENDAR</small><h2>${ready ? "Connected and automatic" : status.configured ? "Ready to connect" : "One-time setup needed"}</h2>
      <p>${ready ? "Accepted weddings are added or updated. Cancelling removes only the Google event; the cancelled booking stays here." : status.configured ? "Connect the Google account whose primary calendar should hold your weddings." : "Add the Google OAuth details to Dockge, redeploy, then return here to connect."}</p></div>
      <span class="v812-calendar-state ${ready ? "ready" : ""}">${ready ? "● Connected" : "○ Not connected"}</span>
    </div>
    ${counts}
    ${problems}
    <div class="v812-calendar-rules">
      <span>✓ Couple names</span><span>✓ First/main venue</span><span>✓ Ceremony time</span><span>✓ No client invitations</span>
    </div>
    ${!status.configured ? `<div class="v812-calendar-setup"><strong>Authorized redirect URI</strong><code>${esc(status.redirect_uri)}</code><small>Copy this exact address into the Google Cloud OAuth Web application.</small></div>` : ""}
    <footer>
      ${ready ? `<button id="google-calendar-sync" class="primary">Sync current bookings</button><button id="google-calendar-disconnect" class="secondary">Disconnect</button>` : status.configured ? `<button id="google-calendar-connect" class="primary">Connect Google Calendar</button>` : ""}
      <small>Testing Mode records and imported Studio Ninja weddings are deliberately excluded.</small>
    </footer>`;
    document.querySelector("#google-calendar-connect")?.addEventListener("click", connectGoogleCalendar);
    document.querySelector("#google-calendar-sync")?.addEventListener("click", syncGoogleCalendar);
    document.querySelector("#google-calendar-disconnect")?.addEventListener("click", disconnectGoogleCalendar);
  }

  async function loadGoogleCalendarStatus() {
    try {
      renderCalendarCard(await api("/api/integrations/google-calendar/status"));
    } catch (error) {
      const host = document.querySelector("#google-calendar-settings");
      if (host) host.innerHTML = `<div class="empty"><strong>Calendar status unavailable</strong>${esc(error.message)}</div>`;
    }
  }

  async function connectGoogleCalendar() {
    const button = document.querySelector("#google-calendar-connect");
    if (button) { button.disabled = true; button.textContent = "Opening Google…"; }
    try {
      const result = await api("/api/integrations/google-calendar/connect");
      location.assign(result.authorization_url);
    } catch (error) {
      toast(error.message, "error");
      if (button) { button.disabled = false; button.textContent = "Connect Google Calendar"; }
    }
  }

  async function syncGoogleCalendar() {
    if (!confirm("Add or update all eligible current BookingSystem2026 weddings in your primary Google Calendar?\n\nCancelled mapped events will be removed. Studio Ninja imports and Testing Mode records will not be touched.")) return;
    const button = document.querySelector("#google-calendar-sync");
    if (button) { button.disabled = true; button.textContent = "Syncing safely…"; }
    try {
      const result = await api("/api/integrations/google-calendar/sync", {method: "POST"});
      toast(`${result.synced} synced · ${result.removed} removed${result.needs_attention ? ` · ${result.needs_attention} need attention` : ""}`, result.needs_attention ? "error" : "");
      await loadGoogleCalendarStatus();
    } catch (error) {
      toast(error.message, "error");
      await loadGoogleCalendarStatus();
    }
  }

  async function disconnectGoogleCalendar() {
    if (!confirm("Disconnect Google Calendar?\n\nExisting Google events will stay in the calendar. Automatic updates will pause until you reconnect.")) return;
    try {
      const result = await api("/api/integrations/google-calendar/disconnect", {method: "POST"});
      toast(result.message);
      await loadGoogleCalendarStatus();
    } catch (error) {
      toast(error.message, "error");
    }
  }

  renderSettings = function () {
    baseRenderSettingsV812();
    const content = document.querySelector("#content");
    if (!content) return;
    content.insertAdjacentHTML("afterbegin", `<section id="google-calendar-settings" class="panel v812-calendar-card"><div class="loading">Checking Google Calendar…</div></section>`);
    loadGoogleCalendarStatus();
    const notice = calendarNotice();
    if (notice) {
      content.insertAdjacentHTML("afterbegin", `<section class="v812-calendar-notice"><strong>${esc(notice[0])}</strong><span>${esc(notice[1])}</span></section>`);
    }
  };
})();
