/* V8.9.6 - unified Hostinger IMAP inbox and booking-aware SMTP replies. */
(() => {
  titles.mail = "Inbox";
  subtitles.mail = "Read and reply from Weddings By Mark and Ivory Digital in one place.";
  state.mailMessages = [];
  state.mailAccounts = [];
  state.mailErrors = {};
  state.mailUnreadOnly = false;
  state.mailSelected = null;
  state.mailLoading = false;
  state.mailLoaded = false;

  const baseRenderV896 = render;
  render = function () {
    const mail = state.view === "mail";
    $("#add-record")?.classList.toggle("hidden", mail);
    if (!mail) return baseRenderV896();
    $("#page-eyebrow").textContent = state.brand === "all" ? "BOTH BUSINESSES" : labels[state.brand].toUpperCase();
    $("#page-title").textContent = titles.mail;
    $("#page-subtitle").textContent = subtitles.mail;
    renderMailWorkspace();
  };

  function mailKey(message) { return `${message.brand}:${message.uid}`; }
  function mailBrandLabel(brand) { return brand === "wbm" ? "Weddings By Mark" : "Ivory Digital"; }
  function mailDate(value) {
    if (!value) return "Unknown date";
    const date = new Date(value);
    const today = new Date();
    return date.toDateString() === today.toDateString()
      ? new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" }).format(date)
      : new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: date.getFullYear() === today.getFullYear() ? undefined : "numeric" }).format(date);
  }
  function mailDateLong(value) {
    if (!value) return "Unknown date";
    return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  }

  async function loadMailWorkspace(force = false) {
    if (state.mailLoading || (state.mailLoaded && !force)) return;
    state.mailLoading = true;
    renderMailWorkspace();
    try {
      const [status, inbox] = await Promise.all([
        api("/api/mail/status"),
        api(`/api/mail/messages?limit=100${state.mailUnreadOnly ? "&unread_only=true" : ""}`)
      ]);
      state.mailAccounts = status.accounts || [];
      state.mailMessages = inbox.messages || [];
      state.mailErrors = inbox.errors || {};
      state.mailLoaded = true;
      const unread = Number(status.unread || 0);
      const badge = $("#mail-nav-count");
      if (badge) {
        badge.textContent = unread > 99 ? "99+" : String(unread);
        badge.classList.toggle("hidden", unread === 0);
      }
    } catch (error) {
      state.mailErrors = { all: error.message };
    } finally {
      state.mailLoading = false;
      if (state.view === "mail") renderMailWorkspace();
    }
  }

  function accountCard(account) {
    const name = mailBrandLabel(account.brand);
    const stateLabel = account.connected ? `${account.unread} unread` : account.configured ? "Connection needs attention" : "Needs setting up";
    return `<article class="mail-account ${account.brand} ${account.connected ? "connected" : "problem"}">
      <i>${account.connected ? "✓" : "!"}</i><span><small>${esc(name)}</small><strong>${esc(account.address || "Mailbox not set")}</strong><em>${esc(stateLabel)}</em></span>
    </article>`;
  }

  function filteredMail() {
    const query = String(state.search || "").trim().toLowerCase();
    return state.mailMessages.filter(message =>
      (state.brand === "all" || message.brand === state.brand) &&
      (!state.mailUnreadOnly || message.unread) &&
      (!query || `${message.from_name} ${message.from_email} ${message.subject} ${message.booking?.title || ""}`.toLowerCase().includes(query))
    );
  }

  function renderMailWorkspace() {
    const content = $("#content");
    if (!content) return;
    if (!state.mailLoaded && !state.mailLoading) {
      content.innerHTML = `<div class="panel loading">Connecting securely to both Hostinger inboxes…</div>`;
      loadMailWorkspace();
      return;
    }
    const rows = filteredMail();
    const selectedKey = state.mailSelected ? mailKey(state.mailSelected) : "";
    const errors = Object.entries(state.mailErrors || {}).map(([brand, text]) => `<div class="mail-error"><strong>${brand === "all" ? "Inbox" : mailBrandLabel(brand)}</strong><span>${esc(text)}</span></div>`).join("");
    content.innerHTML = `<section class="mail-account-strip">${state.mailAccounts.map(accountCard).join("")}</section>
      ${errors}
      <section class="mail-workspace ${state.mailSelected ? "message-open" : ""}">
        <aside class="mail-list-panel">
          <header class="mail-list-header"><div><small>LIVE HOSTINGER MAIL</small><h2>${state.mailUnreadOnly ? "Unread" : "Inbox"}</h2></div><div>
            <button id="mail-unread-toggle" class="secondary ${state.mailUnreadOnly ? "active" : ""}">${state.mailUnreadOnly ? "Show all" : "Unread only"}</button>
            <button id="mail-refresh" class="secondary" ${state.mailLoading ? "disabled" : ""}>${state.mailLoading ? "Refreshing…" : "↻ Refresh"}</button>
          </div></header>
          <div class="mail-list">${rows.map(message => `<button class="mail-row ${message.unread ? "unread" : ""} ${mailKey(message) === selectedKey ? "active" : ""}" data-mail-brand="${message.brand}" data-mail-uid="${message.uid}">
            <i class="mail-unread-dot"></i><span class="mail-row-main"><span><strong>${esc(message.from_name || message.from_email)}</strong><time>${esc(mailDate(message.date))}</time></span><b>${esc(message.subject)}</b><small>${esc(message.from_email)}</small>${message.booking ? `<em>Linked to ${esc(message.booking.title)}</em>` : `<em class="unmatched">Not matched to a booking</em>`}</span><span class="mail-brand ${message.brand}">${message.brand === "wbm" ? "WBM" : "IVORY"}</span>
          </button>`).join("") || `<div class="empty mail-empty"><strong>${state.mailUnreadOnly ? "No unread emails" : "No emails found"}</strong>${state.search ? "Try clearing the search box." : "New messages will appear here when they reach Hostinger."}</div>`}</div>
        </aside>
        <main id="mail-reader" class="mail-reader">${state.mailSelected ? mailReaderLoading() : `<div class="mail-reader-empty"><i>✉</i><strong>Choose an email</strong><span>Open a message to read it, see its matching booking and reply from the correct business address.</span></div>`}</main>
      </section>`;
    $$("[data-mail-uid]", content).forEach(button => button.onclick = () => openMailMessage(button.dataset.mailBrand, button.dataset.mailUid));
    $("#mail-refresh")?.addEventListener("click", () => loadMailWorkspace(true));
    $("#mail-unread-toggle")?.addEventListener("click", () => {
      state.mailUnreadOnly = !state.mailUnreadOnly;
      state.mailLoaded = false;
      state.mailSelected = null;
      renderMailWorkspace();
    });
    if (state.mailSelected) renderMailReader(state.mailSelected);
  }

  function mailReaderLoading() {
    return `<div class="mail-reader-empty"><span class="mail-spinner"></span><strong>Opening email…</strong></div>`;
  }

  async function openMailMessage(brand, uid) {
    state.mailSelected = { brand, uid, loading: true };
    renderMailWorkspace();
    try {
      const message = await api(`/api/mail/${brand}/messages/${uid}`);
      state.mailSelected = message;
      const listed = state.mailMessages.find(item => item.brand === brand && item.uid === uid);
      if (listed) listed.unread = false;
      renderMailWorkspace();
    } catch (error) {
      state.mailSelected = null;
      toast(error.message, "error");
      renderMailWorkspace();
    }
  }

  function sentReplyCard(reply) {
    return `<article class="mail-sent-reply"><header><strong>You replied</strong><time>${esc(mailDateLong(reply.sent_at))}</time></header><p>${esc(reply.body).replace(/\n/g, "<br>")}</p><small>${reply.copied_to_sent ? "Saved in Hostinger Sent" : "Saved safely in this booking system"}</small></article>`;
  }

  function renderMailReader(message) {
    const reader = $("#mail-reader");
    if (!reader || !message || message.loading) return;
    const booking = message.booking;
    const imported = booking?.legacy_source === "studio_ninja";
    reader.innerHTML = `<button id="mail-reader-back" class="mail-reader-back">← Back to inbox</button>
      <header class="mail-message-head ${message.brand}">
        <div class="mail-sender-avatar">${esc((message.from_name || message.from_email || "?").slice(0, 2).toUpperCase())}</div>
        <div><small>${esc(mailBrandLabel(message.brand))}</small><h2>${esc(message.subject)}</h2><p><strong>${esc(message.from_name || message.from_email)}</strong> &lt;${esc(message.from_email)}&gt;</p><time>${esc(mailDateLong(message.date))}</time></div>
        <button id="mail-mark-unread" class="secondary">Mark unread</button>
      </header>
      ${booking ? `<button class="mail-booking-link ${imported ? "legacy" : ""}" id="mail-open-booking"><span><small>${imported ? "IMPORTED · MANUAL COMMUNICATION ONLY" : "MATCHED BOOKING"}</small><strong>${esc(booking.title)}</strong><em>${esc(booking.event_date ? fmtDate(booking.event_date) : statusText(booking.status))}</em></span><b>Open booking →</b></button>` : `<section class="mail-unmatched"><strong>This sender is not matched to a booking</strong><span>You can still reply safely. If they later enquire using this same email address, future messages will match automatically.</span></section>`}
      <article class="mail-message-body">${esc(message.body).replace(/\n/g, "<br>")}</article>
      ${message.attachments?.length ? `<section class="mail-attachments"><strong>Attachments</strong>${message.attachments.map(file => `<a href="/api/mail/${message.brand}/messages/${message.uid}/attachments/${file.index}"><span>▤ ${esc(file.filename)}</span><small>${esc(bytes(file.size))}</small></a>`).join("")}</section>` : ""}
      ${(message.replies || []).length ? `<section class="mail-reply-history"><h3>Your replies in this conversation</h3>${message.replies.map(sentReplyCard).join("")}</section>` : ""}
      <form id="mail-reply-form" class="mail-reply-composer">
        <header><div><small>REPLY FROM</small><strong>${esc(message.brand === "wbm" ? "mark@perfectweddingsbymark.uk" : "admin@ivorydigital.uk")}</strong></div><span>To ${esc(message.reply_to_email)}</span></header>
        <textarea id="mail-reply-body" rows="7" maxlength="20000" required placeholder="Write your reply here…"></textarea>
        <footer>${booking ? imported ? `<div class="mail-import-safety"><strong>No account link will be added</strong><span>This Studio Ninja client remains manual-only.</span></div>` : message.account_link_available ? `<label class="mail-link-option"><input id="mail-include-link" type="checkbox" checked><span><strong>Include their secure account button</strong><small>Uses the correct link for this booking.</small></span></label>` : "" : `<span class="muted">No booking link will be added.</span>`}<button id="mail-send-reply" class="primary" type="submit">Send reply</button></footer>
      </form>`;
    $("#mail-reader-back").onclick = () => { state.mailSelected = null; renderMailWorkspace(); };
    $("#mail-mark-unread").onclick = async () => {
      try {
        await api(`/api/mail/${message.brand}/messages/${message.uid}/seen`, { method: "PATCH", body: JSON.stringify({ seen: false }) });
        const listed = state.mailMessages.find(item => item.brand === message.brand && item.uid === message.uid);
        if (listed) listed.unread = true;
        toast("Email marked unread");
        state.mailSelected = null;
        renderMailWorkspace();
      } catch (error) { toast(error.message, "error"); }
    };
    if ($("#mail-open-booking")) $("#mail-open-booking").onclick = () => openDrawer(booking.id, "Overview");
    $("#mail-reply-form").onsubmit = async event => {
      event.preventDefault();
      const button = $("#mail-send-reply");
      button.disabled = true;
      button.textContent = "Sending…";
      try {
        const result = await api(`/api/mail/${message.brand}/messages/${message.uid}/reply`, {
          method: "POST",
          body: JSON.stringify({
            body: value("#mail-reply-body").trim(),
            booking_id: booking?.id || null,
            include_account_link: Boolean($("#mail-include-link")?.checked)
          })
        });
        toast(result.account_link_skipped_for_import ? "Reply sent safely without creating a client link" : "Reply sent from your booking system");
        await openMailMessage(message.brand, message.uid);
      } catch (error) {
        button.disabled = false;
        button.textContent = "Send reply";
        toast(error.message, "error");
      }
    };
  }

  const baseOpenDrawerV896 = openDrawer;
  openDrawer = async function (id, tab = "Overview") {
    await baseOpenDrawerV896(id, tab);
    const record = state.current;
    const emailAction = $(".record-contact-actions a[href^='mailto:']", $("#drawer"));
    if (emailAction && record) {
      emailAction.removeAttribute("href");
      emailAction.setAttribute("role", "button");
      emailAction.textContent = "✉ Inbox";
      emailAction.onclick = () => {
        closeDrawer();
        state.search = record.client.email.toLowerCase();
        $("#search").value = record.client.email;
        navigate("mail");
      };
    }
  };
})();
