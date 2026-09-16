/* V8.49 - The SMS Works text centre, replies and opt-in automations. */
(() => {
  "use strict";

  function smsEstimateV849(message) {
    const text = String(message || "");
    const unicode = /[^\x00-\x7F]/.test(text);
    const single = unicode ? 70 : 160;
    const joined = unicode ? 67 : 153;
    const parts = text.length <= single ? 1 : Math.ceil(text.length / joined);
    return {characters: text.length, parts, unicode};
  }

  function smsStatusLabelV849(status) {
    return ({
      sending: "Sending", sent: "Sent to network", delivered: "Delivered",
      failed: "Failed", undeliverable: "Not delivered", expired: "Expired",
      rejected: "Rejected", received: "Reply received", scheduled: "Scheduled",
    })[status] || statusText(status);
  }

  function setupSummaryV849(status) {
    if (status.sender_error) {
      return `<strong>SMS sender needs attention</strong><span>${esc(status.sender_error)}. Nothing can send until this is corrected.</span>`;
    }
    if (status.ready && status.reply_capable) {
      return `<strong>SMS ready with replies</strong><span>Texts send from ${esc(status.sender)} and couple replies return to their booking.</span>`;
    }
    if (status.ready) {
      return `<strong>SMS ready · branded one-way sender</strong><span>Couples see ${esc(status.sender)}. Add an SMS Works reply number when you want replies inside the booking.</span>`;
    }
    return `<strong>SMS is safely switched off</strong><span>Nothing can be sent until The SMS Works token is added and SMS_ENABLED is deliberately set to true.</span>`;
  }

  function historyRowV849(message) {
    const incoming = message.direction === "incoming";
    const when = message.received_at || message.sent_at || message.created_at;
    return `<article class="v849-message ${incoming ? "incoming" : "outgoing"} ${attr(message.status)}">
      <i>${incoming ? "←" : "→"}</i>
      <span><small>${incoming ? "COUPLE REPLIED" : message.automated ? "AUTOMATIC TEXT" : "TEXT SENT BY YOU"}</small>
      <p>${esc(message.body)}</p><em>${esc(smsStatusLabelV849(message.status))} · ${esc(fmtDateTime(when))}${message.parts ? ` · ${message.parts} credit${message.parts === 1 ? "" : "s"}` : ""}</em>
      ${message.error ? `<b>${esc(message.error)}</b>` : ""}</span>
    </article>`;
  }

  function automationRowV849(record, item, status) {
    const protectedRecord = Boolean(record.legacy_source);
    const state = protectedRecord ? "Protected" : item.paused ? "Paused for this couple" : item.active ? "Ready" : "Off in master template";
    return `<article class="v849-automation ${item.paused || protectedRecord || !item.active ? "paused" : "ready"}">
      <i>${protectedRecord ? "🔒" : item.paused ? "Ⅱ" : item.active ? "✓" : "○"}</i>
      <span><strong>${esc(item.label)}</strong><small>${esc(state)}${!status.automatic_enabled ? " · automatic SMS globally off" : ""}</small></span>
      ${protectedRecord ? `<em>MANUAL ONLY</em>` : `<button type="button" class="${item.paused ? "primary" : "secondary"}" data-sms-automation="${attr(item.template_key)}" data-paused="${item.paused ? "1" : "0"}">${item.paused ? "Resume this text" : "Pause this text"}</button>`}
    </article>`;
  }

  function openSmsComposerV849(record, data, renderAgain) {
    const templates = data.templates || [];
    const preferred = templates.find(item => item.template_key === "manual_message") || templates[0];
    if (!preferred) return toast("No SMS template is available", "error");
    const options = templates.map(item => `<option value="${attr(item.template_key)}" ${item === preferred ? "selected" : ""}>${esc(item.display_name)}${item.is_automatic ? " (automatic wording)" : ""}</option>`).join("");
    showModal(
      `Text ${record.title}`,
      `<section class="full v849-recipient"><small>TO</small><strong>${esc(data.client_phone || "No mobile number")}</strong><span>${data.is_test ? "TEST booking - safely redirected to your test number." : data.status.reply_capable ? "They can reply and it will appear in this booking." : `They will see ${esc(data.status.sender)}; this sender cannot receive replies.`}</span></section>
       <label class="full">Start with<select id="v849-compose-template">${options}</select></label>
       <label class="full">Exact text<textarea id="v849-compose-body" rows="8" maxlength="1280" required>${esc(preferred.rendered_body)}</textarea><small id="v849-compose-count" class="field-help"></small></label>
       <label class="full check-option v849-confirm"><input id="v849-compose-confirm" type="checkbox" required><span>I have checked the mobile number and exact message.</span></label>`,
      async () => {
        const result = await api(`/api/bookings/${record.id}/sms/send`, {
          method: "POST",
          body: JSON.stringify({
            body: value("#v849-compose-body").trim(),
            template_key: value("#v849-compose-template"),
            confirmed: Boolean($("#v849-compose-confirm")?.checked),
          }),
        });
        closeModal();
        toast(result.message.status === "sent" ? "Text sent to the mobile network" : "Text saved");
        await renderAgain();
      },
      "Nothing is sent until you review the wording and press Send text."
    );
    const sendButton = $("#dynamic-form button[type='submit']");
    if (sendButton) sendButton.textContent = "Send text";
    const select = $("#v849-compose-template");
    const body = $("#v849-compose-body");
    const count = $("#v849-compose-count");
    const updateCount = () => {
      const estimate = smsEstimateV849(body.value);
      count.textContent = `${estimate.characters} characters · about ${estimate.parts} SMS credit${estimate.parts === 1 ? "" : "s"}${estimate.unicode ? " · Unicode/emoji uses shorter segments" : ""}`;
    };
    select.onchange = () => {
      const template = templates.find(item => item.template_key === select.value);
      if (template) body.value = template.rendered_body;
      updateCount();
    };
    body.oninput = updateCount;
    updateCount();
  }

  async function renderSmsCentreV849(record, body) {
    body.innerHTML = `<div class="panel loading">Loading texts with this couple…</div>`;
    try {
      const data = await api(`/api/bookings/${record.id}/sms`);
      const status = data.status;
      const canSend = status.ready && !data.phone_error && record.status !== "cancelled";
      const rerender = () => renderSmsCentreV849(record, body);
      body.innerHTML = `<section class="v849-centre">
        <header class="v849-head"><div><small>TEXT MESSAGES</small><h3>Texts with ${esc(data.client_name)}</h3><p>Send a quick message, see delivery, and keep any replies with the correct booking.</p></div><button type="button" class="primary" data-v849-compose ${canSend ? "" : "disabled"}>▣ Write text</button></header>
        <section class="v849-status ${status.ready ? "ready" : "off"}"><i>${status.ready ? "✓" : "○"}</i><span>${setupSummaryV849(status)}</span>${data.phone_error ? `<b>${esc(data.phone_error)}</b>` : ""}</section>
        ${data.is_test ? `<div class="v849-safe-banner"><strong>TEST BOOKING</strong><span>No text can go to the client number; it is redirected to your nominated test mobile.</span></div>` : ""}
        ${data.legacy_manual_only ? `<div class="v849-safe-banner"><strong>STUDIO NINJA IMPORT · MANUAL ONLY</strong><span>You may send one text yourself, but automatic SMS remains permanently blocked for this booking.</span></div>` : ""}
        <section class="v849-history"><header><div><small>CONVERSATION</small><h3>Complete text history</h3></div><b>${data.messages.length}</b></header><div>${data.messages.map(historyRowV849).join("") || `<div class="empty small-empty"><strong>No texts yet</strong>Your sent messages and couple replies will appear here.</div>`}</div></section>
        <section class="v849-automations"><header><div><small>AUTOMATIC TEXT CONTROLS</small><h3>Pause each text separately</h3><p>These switches affect SMS only. Your existing email reminders continue exactly as before.</p></div><b>${status.automatic_enabled ? "MASTER ON" : "MASTER OFF"}</b></header><div>${data.automations.map(item => automationRowV849(record, item, status)).join("")}</div></section>
      </section>`;
      $("[data-v849-compose]", body)?.addEventListener("click", () => openSmsComposerV849(record, data, rerender));
      $$('[data-sms-automation]', body).forEach(button => button.onclick = async () => {
        const paused = button.dataset.paused === "1";
        const row = button.closest("article");
        const label = row.querySelector("strong")?.textContent || "this automatic text";
        if (!confirm(`${paused ? "Resume" : "Pause"} ${label} for ${record.title}?\n\nThis changes SMS only and sends nothing now.`)) return;
        button.disabled = true;
        try {
          const result = await api(`/api/bookings/${record.id}/sms/automations/${encodeURIComponent(button.dataset.smsAutomation)}`, {
            method: "PUT", body: JSON.stringify({paused: !paused}),
          });
          toast(result.message);
          await rerender();
        } catch (error) {
          button.disabled = false;
          toast(error.message, "error");
        }
      });
    } catch (error) {
      body.innerHTML = `<div class="v844-section-error"><strong>Texts could not be displayed</strong><span>${esc(error.message)}</span><button type="button" class="secondary" data-v849-retry>Try again</button></div>`;
      $("[data-v849-retry]", body).onclick = () => renderSmsCentreV849(record, body);
    }
  }

  function editSmsTemplateV849(template) {
    showModal(
      `Edit ${template.display_name}`,
      `<label>Type<input value="${template.is_automatic ? "Automatic SMS" : "Manual SMS"}" readonly></label>
       <label>Status<select id="v849-template-active"><option value="true" ${template.is_active ? "selected" : ""}>Active</option><option value="false" ${template.is_active ? "" : "selected"}>Inactive</option></select></label>
       <label class="full">Template name<input id="v849-template-name" maxlength="140" value="${attr(template.display_name)}" required></label>
       <label class="full">Text wording<textarea id="v849-template-body" rows="8" maxlength="1280" required>${esc(template.body)}</textarea><small id="v849-template-count" class="field-help"></small></label>`,
      async () => {
        await api(`/api/sms/templates/${template.id}`, {method: "PATCH", body: JSON.stringify({
          display_name: value("#v849-template-name").trim(),
          body: value("#v849-template-body").trim(),
          is_active: value("#v849-template-active") === "true",
        })});
        closeModal();
        toast("SMS template saved");
        renderCommunicationsV2();
      },
      template.is_automatic ? "Active means this type may send only when the global automatic-SMS switch is also on and the couple's individual switch is not paused." : "This wording is only used after you deliberately open a booking, review it and press Send text."
    );
    const body = $("#v849-template-body"), count = $("#v849-template-count");
    const update = () => {
      const result = smsEstimateV849(body.value);
      count.textContent = `${result.characters} characters · about ${result.parts} SMS credit${result.parts === 1 ? "" : "s"}${result.unicode ? " · Unicode/emoji" : ""}`;
    };
    body.oninput = update;
    update();
  }

  async function appendSmsTemplatesV849() {
    const content = $("#content");
    if (!content || state.view !== "communications" || $(".v849-template-panel", content)) return;
    const loading = document.createElement("section");
    loading.className = "panel v849-template-panel loading";
    loading.textContent = "Loading SMS templates…";
    content.append(loading);
    try {
      const query = state.brand === "all" ? "" : `?brand=${encodeURIComponent(state.brand)}`;
      const data = await api(`/api/sms/templates${query}`);
      if (state.view !== "communications") return;
      const status = data.status;
      loading.className = "panel v849-template-panel";
      loading.innerHTML = `<div class="panel-title"><div><small>THE SMS WORKS</small><h2>SMS templates</h2><p>Manual messages and every optional automatic text are controlled separately.</p></div><span class="v849-provider-state ${status.ready ? "ready" : "off"}">${status.ready ? "READY" : "SAFELY OFF"}</span></div>
        <div class="v849-master-note"><span>${setupSummaryV849(status)}</span><b>Automatic SMS: ${status.automatic_enabled ? "ON" : "OFF"}</b></div>
        <div class="template-list">${data.templates.map(template => `<article class="template-row-v8 ${template.is_active ? "" : "template-inactive"}"><i class="brand-badge ${template.brand}">SMS</i><span><strong>${esc(template.display_name)}${template.is_active ? "" : " <em>INACTIVE</em>"}</strong><small>${esc(template.body)}</small><small class="v817-template-usage"><b class="${template.is_automatic ? "automatic" : "manual"}">${template.is_automatic ? "AUTOMATIC" : "MANUAL OPTION"}</b>${template.estimate.characters} characters · about ${template.estimate.parts} credit${template.estimate.parts === 1 ? "" : "s"}</small><small>Key: ${esc(template.template_key)}</small></span><div class="template-actions"><button class="mini" data-v849-template="${attr(template.id)}">Edit</button></div></article>`).join("") || `<div class="empty"><strong>SMS is currently for Weddings By Mark</strong>Choose Weddings By Mark or All businesses to see the templates.</div>`}</div>`;
      $$('[data-v849-template]', loading).forEach(button => button.onclick = () => editSmsTemplateV849(data.templates.find(item => item.id === button.dataset.v849Template)));
    } catch (error) {
      loading.className = "panel v849-template-panel";
      loading.innerHTML = `<div class="empty"><strong>SMS templates unavailable</strong>${esc(error.message)}</div>`;
    }
  }

  function smsSettingsCardV849(status) {
    return `<section class="panel v849-settings-card"><header><div><small>THE SMS WORKS · V8.49</small><h2>Text messaging</h2><p>Send from a booking, keep delivery evidence, and receive replies when your SMS Works reply number is active.</p></div><span class="v849-provider-state ${status.ready ? "ready" : "off"}">${status.ready ? "READY" : "SAFELY OFF"}</span></header>
      <div class="v849-settings-grid"><article><small>SENDER</small><strong>${esc(status.sender)}</strong><span>${status.reply_capable ? "Two-way reply number" : "Branded one-way name"}</span></article><article><small>AUTOMATIC TEXTS</small><strong>${status.automatic_enabled ? "Enabled" : "Off"}</strong><span>Each template and couple also has its own switch</span></article><article><small>WEBHOOK SECURITY</small><strong>${status.webhook_secured ? "Ready" : "Not configured"}</strong><span>${status.reply_capable ? "Needed for replies" : "Needed when reply number is added"}</span></article></div>
      ${status.ready ? `<div class="v849-settings-ready"><strong>✓ Provider connection is enabled</strong><span>${status.reply_capable ? "Couple replies will be matched using the booking reference attached to each outgoing text." : "You can send as WedsByMark now. Ask The SMS Works for a virtual reply number when you are ready for two-way conversations."}</span></div>` : `<div class="v849-setup"><strong>One-time TrueNAS setup</strong><ol><li>Create your The SMS Works account and generate its JSON Web Token.</li><li>Add <code>SMS_API_TOKEN</code> to the booking app environment. Never paste it into a chat or screenshot.</li><li>Add <code>SMS_ENABLED=true</code>, rebuild, then send only from a TEST booking first.</li><li>When your reply number arrives, add <code>SMS_REPLY_NUMBER</code>, <code>SMS_WEBHOOK_USERNAME</code> and <code>SMS_WEBHOOK_PASSWORD</code>.</li></ol></div>`}
      <footer><span>Delivery webhook</span><code>${esc(status.delivery_webhook_url)}</code><span>Reply webhook</span><code>${esc(status.incoming_webhook_url)}</code></footer></section>`;
  }

  async function loadSmsSettingsV849() {
    const content = $("#content");
    if (!content || state.view !== "settings" || $(".v849-settings-card", content)) return;
    try {
      const status = await api("/api/sms/status");
      if (state.view === "settings") content.insertAdjacentHTML("afterbegin", smsSettingsCardV849(status));
    } catch (error) {
      if (state.view === "settings") content.insertAdjacentHTML("afterbegin", `<section class="panel v849-settings-card"><div class="empty"><strong>SMS status unavailable</strong>${esc(error.message)}</div></section>`);
    }
  }

  const baseRenderCommunicationsV849 = renderCommunicationsV2;
  renderCommunicationsV2 = async function () {
    await baseRenderCommunicationsV849();
    await appendSmsTemplatesV849();
  };

  const baseRenderSettingsV849 = renderSettings;
  renderSettings = function () {
    baseRenderSettingsV849();
    loadSmsSettingsV849();
  };

  window.WBMSmsV849 = Object.freeze({version: "8.49", render: renderSmsCentreV849});
})();
