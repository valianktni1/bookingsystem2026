/* V8.46 - protected after-wedding delivery and completion workflow. */
(() => {
  "use strict";

  const baseRenderTabV846 = renderTab;
  const baseRenderRecordsV846 = renderRecords;

  renderRecords = function () {
    baseRenderRecordsV846();
    if (!["enquiries", "weddings"].includes(state.view)) return;
    $$("[data-record]", $("#content")).forEach(row => {
      const record = state.records.find(item => item.id === row.dataset.record);
      const dateCell = row.querySelector(".booking-date-cell > span:first-child");
      if (record?.kind === "wedding" && dateCell) {
        dateCell.textContent = fmtEventDate(record.event_date);
      }
    });
  };

  function localTodayV846() {
    const now = new Date();
    const offset = now.getTimezoneOffset() * 60000;
    return new Date(now.getTime() - offset).toISOString().slice(0, 10);
  }

  function afterWeddingAppliesV846(record) {
    if (!record || record.brand !== "wbm" || record.kind !== "wedding") return false;
    if (["enquiry", "quoted", "cancelled"].includes(record.status)) return false;
    return record.status === "completed"
      || Boolean(record.workflow_state?.after_wedding)
      || Boolean(record.event_date && record.event_date <= localTodayV846());
  }

  function deliveryLabelV846(item, kind) {
    if (item.status === "delivered") {
      return `Delivered${item.delivered_on ? ` · ${fmtDate(item.delivered_on)}` : ""}`;
    }
    if (item.status === "not_required") return "Not required";
    if (kind === "album") return item.status_label || statusText(item.status);
    return "Waiting to be delivered";
  }

  function deliveryLinkV846(url, label) {
    return url ? `<a href="${attr(url)}" target="_blank" rel="noopener">Open ${esc(label)} ↗</a>` : "";
  }

  function readinessRowsV846(readiness) {
    return (readiness.checks || []).map(check => `<span class="${check.complete ? "complete" : "waiting"}"><i>${check.complete ? "✓" : "○"}</i>${esc(check.label)}</span>`).join("");
  }

  function setModalButtonV846(label) {
    const button = $("#dynamic-form footer .primary");
    if (button) button.textContent = label;
  }

  async function saveAfterWeddingV846(record, data, body) {
    const stateData = data.state;
    showModal(
      "Update after-wedding progress",
      `<section class="full v846-modal-note"><strong>Private working record</strong><span>Saving these details does not email the couple, alter an invoice or change their files.</span></section>
       <label>Photographs<select id="v846-photos-status"><option value="pending" ${stateData.photos.status === "pending" ? "selected" : ""}>Waiting to be delivered</option><option value="delivered" ${stateData.photos.status === "delivered" ? "selected" : ""}>Delivered</option></select></label>
       <label>Photo delivery date<input id="v846-photos-date" type="date" value="${attr(stateData.photos.delivered_on || "")}"></label>
       <label class="full">Gallery link<input id="v846-gallery-url" type="url" maxlength="2000" value="${attr(stateData.photos.gallery_url || "")}" placeholder="https://weddingsbymark.uk/..."></label>
       <label>Video / wedding film<select id="v846-video-status"><option value="not_required" ${stateData.video.status === "not_required" ? "selected" : ""}>Not required for this package</option><option value="pending" ${stateData.video.status === "pending" ? "selected" : ""}>Waiting to be delivered</option><option value="delivered" ${stateData.video.status === "delivered" ? "selected" : ""}>Delivered</option></select></label>
       <label>Video delivery date<input id="v846-video-date" type="date" value="${attr(stateData.video.delivered_on || "")}"></label>
       <label class="full">Video link (optional)<input id="v846-video-url" type="url" maxlength="2000" value="${attr(stateData.video.video_url || "")}" placeholder="https://..."></label>
       <label>Wedding album<select id="v846-album-status"><option value="not_required" ${stateData.album.status === "not_required" ? "selected" : ""}>Not required</option><option value="awaiting_selection" ${stateData.album.status === "awaiting_selection" ? "selected" : ""}>Awaiting image choices</option><option value="designing" ${stateData.album.status === "designing" ? "selected" : ""}>Designing album</option><option value="ordered" ${stateData.album.status === "ordered" ? "selected" : ""}>Ordered from supplier</option><option value="delivered" ${stateData.album.status === "delivered" ? "selected" : ""}>Delivered</option></select></label>
       <label>Album delivery date<input id="v846-album-date" type="date" value="${attr(stateData.album.delivered_on || "")}"></label>
       <label class="full">Album notes<textarea id="v846-album-notes" maxlength="2000" rows="3" placeholder="Image choices received, design approved, supplier order number…">${esc(stateData.album.notes || "")}</textarea></label>`,
      async () => {
        const result = await api(`/api/bookings/${record.id}/after-wedding`, {
          method: "PUT",
          body: JSON.stringify({
            photos_status: value("#v846-photos-status"),
            photos_delivered_on: nullable(value("#v846-photos-date")),
            gallery_url: nullable(value("#v846-gallery-url")),
            video_status: value("#v846-video-status"),
            video_delivered_on: nullable(value("#v846-video-date")),
            video_url: nullable(value("#v846-video-url")),
            album_status: value("#v846-album-status"),
            album_delivered_on: nullable(value("#v846-album-date")),
            album_notes: nullable(value("#v846-album-notes")),
          }),
        });
        closeModal();
        await refresh();
        toast("After-wedding progress saved · no email sent");
        renderAfterWeddingV846(state.current || record, body, result);
      },
      "Delivery dates and links are private to your admin booking record."
    );
    setModalButtonV846("Save progress");
  }

  async function sendReviewRequestV846(record, body) {
    try {
      const centre = await api(`/api/bookings/${record.id}/email-centre`);
      const template = (centre.templates || []).find(item => item.template_key === "review_request");
      if (!template) throw new Error("The After-wedding review request template is missing or inactive");
      showModal(
        "Review the review-request email",
        `<section class="full v846-recipient"><small>TO</small><strong>${esc(centre.recipient)}</strong><span>Nothing is sent until you press Send review request.</span></section>
         <label class="full">Subject<input id="v846-review-subject" maxlength="240" value="${attr(template.subject)}" required></label>
         <label class="full">Message<textarea id="v846-review-body" maxlength="20000" rows="16" required>${esc(template.body)}</textarea><small class="field-help">Personalise this couple's copy here. Your saved master template remains unchanged.</small></label>`,
        async () => {
          const sendButton = $("#dynamic-form button[type='submit']");
          sendButton.disabled = true;
          sendButton.textContent = "Sending…";
          try {
            await api(`/api/bookings/${record.id}/email-centre/send`, {
              method: "POST",
              body: JSON.stringify({
                mode: "template",
                template_key: "review_request",
                subject: value("#v846-review-subject").trim(),
                body: value("#v846-review-body").trim(),
              }),
            });
            closeModal();
            toast("Review request sent and recorded");
            await renderAfterWeddingV846(record, body);
          } catch (error) {
            sendButton.disabled = false;
            sendButton.textContent = "Send review request";
            throw error;
          }
        },
        `Review the exact wording for ${centre.client_name}. This is never an automatic email.`
      );
      setModalButtonV846("Send review request");
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function completeWeddingV846(record) {
    if (!confirm(`Mark ${record.title} as completed?\n\nAll delivery work and the account are clear. The booking, invoice numbers, payments, agreement, emails and files remain permanently retained. Nothing is emailed.`)) return;
    try {
      await api(`/api/bookings/${record.id}/complete`, {method: "POST"});
      await refresh();
      toast("Wedding marked complete · no email sent");
      await openDrawer(record.id, "Overview");
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function renderAfterWeddingV846(record, body, supplied = null) {
    if (!body || !afterWeddingAppliesV846(record)) return;
    let data = supplied;
    try {
      data = data || await api(`/api/bookings/${record.id}/after-wedding`);
    } catch (error) {
      if (!body.isConnected) return;
      body.insertAdjacentHTML("beforeend", `<section class="v846-after-wedding error"><strong>After-wedding workflow unavailable</strong><span>${esc(error.message)}</span></section>`);
      return;
    }
    if (!body.isConnected || !data.eligible) return;
    body.querySelector(".v846-after-wedding")?.remove();
    const stateData = data.state;
    const ready = data.readiness.ready_to_complete;
    const panel = document.createElement("section");
    panel.className = `v846-after-wedding ${data.completed ? "completed" : ready ? "ready" : ""}`;
    panel.innerHTML = `<header><div><small>FINAL STEP · AFTER THE WEDDING</small><h3>${data.completed ? "Wedding work completed" : "Finish and deliver this wedding"}</h3><p>Keep delivery, album and review progress together before closing the job.</p></div><b>${data.readiness.completed_count}/${data.readiness.check_count} ready</b></header>
      <div class="v846-delivery-grid">
        <article class="${stateData.photos.status === "delivered" ? "complete" : "waiting"}"><i>${stateData.photos.status === "delivered" ? "✓" : "1"}</i><span><small>PHOTOGRAPHS</small><strong>${esc(deliveryLabelV846(stateData.photos, "photos"))}</strong>${deliveryLinkV846(stateData.photos.gallery_url, "gallery")}</span></article>
        <article class="${["delivered", "not_required"].includes(stateData.video.status) ? "complete" : "waiting"}"><i>${["delivered", "not_required"].includes(stateData.video.status) ? "✓" : "2"}</i><span><small>VIDEO / FILMS</small><strong>${esc(deliveryLabelV846(stateData.video, "video"))}</strong>${deliveryLinkV846(stateData.video.video_url, "video")}</span></article>
        <article class="${["delivered", "not_required"].includes(stateData.album.status) ? "complete" : "waiting"}"><i>${["delivered", "not_required"].includes(stateData.album.status) ? "✓" : "3"}</i><span><small>WEDDING ALBUM</small><strong>${esc(deliveryLabelV846(stateData.album, "album"))}</strong>${stateData.album.notes ? `<em>${esc(stateData.album.notes)}</em>` : ""}</span></article>
        <article class="${stateData.review_request.status === "sent" ? "complete" : "optional"}"><i>${stateData.review_request.status === "sent" ? "✓" : "☆"}</i><span><small>REVIEW REQUEST · OPTIONAL</small><strong>${stateData.review_request.status === "sent" ? `Sent ${fmtDateTime(stateData.review_request.sent_at)}` : "Not sent"}</strong><em>This never blocks completion.</em></span></article>
      </div>
      <div class="v846-readiness">${readinessRowsV846(data.readiness)}</div>
      ${data.manual_only ? `<div class="v846-manual-note"><strong>Studio Ninja protection remains on</strong><span>Delivery tracking is available here. Any review email must still be sent deliberately through Email client with the usual manual confirmation.</span></div>` : ""}
      <footer><button type="button" class="secondary" data-v846-edit>Update delivery &amp; album</button>${!data.manual_only ? `<button type="button" class="secondary" data-v846-review ${stateData.photos.status !== "delivered" ? "disabled" : ""}>${stateData.review_request.status === "sent" ? "Review & send again" : "Review & send review request"}</button>` : ""}${data.completed ? `<span class="v846-complete-label">✓ Completed and safely retained</span>` : `<button type="button" class="primary" data-v846-complete ${ready ? "" : "disabled"}>${ready ? "Mark wedding complete" : `${data.readiness.blockers.length} thing${data.readiness.blockers.length === 1 ? "" : "s"} still to finish`}</button>`}</footer>`;
    const anchor = body.querySelector(".v823-final-call-pack") || body.querySelector(".v820-final");
    if (anchor) anchor.insertAdjacentElement("afterend", panel);
    else body.append(panel);
    const oldCompletion = $(".record-primary-actions .v830-complete-wedding", $("#drawer"));
    if (oldCompletion && !data.completed) oldCompletion.hidden = true;
    $("[data-v846-edit]", panel).onclick = () => saveAfterWeddingV846(record, data, body);
    const reviewButton = $("[data-v846-review]", panel);
    if (reviewButton && !reviewButton.disabled) reviewButton.onclick = () => sendReviewRequestV846(record, body);
    const completeButton = $("[data-v846-complete]", panel);
    if (completeButton && !completeButton.disabled) completeButton.onclick = () => completeWeddingV846(record);
  }

  async function renderAfterWeddingOverviewV846(record, body) {
    if (!body || !afterWeddingAppliesV846(record)) return;
    try {
      const data = await api(`/api/bookings/${record.id}/after-wedding`);
      if (!body.isConnected || !data.eligible || body.querySelector(".v846-overview-card")) return;
      const card = document.createElement("section");
      card.className = `v846-overview-card ${data.completed ? "completed" : data.readiness.ready_to_complete ? "ready" : ""}`;
      card.innerHTML = `<i>${data.completed ? "✓" : "↗"}</i><div><small>AFTER-WEDDING WORKFLOW</small><strong>${data.completed ? "Wedding completed and retained" : `${data.readiness.completed_count}/${data.readiness.check_count} completion checks clear`}</strong><span>${data.completed ? "Delivery history, invoices, emails and signed records remain safely available." : data.readiness.blockers.join(" · ") || "Everything is ready for completion."}</span></div><button type="button" class="${data.readiness.ready_to_complete ? "primary" : "secondary"}">Open after-wedding workflow</button>`;
      body.prepend(card);
      card.querySelector("button").onclick = async () => {
        await selectRecordTab(record, "Journey", true);
        setTimeout(() => $(".v846-after-wedding")?.scrollIntoView({behavior: "smooth", block: "start"}), 40);
      };
    } catch (_) {
      // The ordinary booking Overview must remain usable if this optional
      // summary cannot be loaded.
    }
  }

  renderTab = async function (record, tab, target = null) {
    await baseRenderTabV846(record, tab, target);
    const body = target || $("#drawer-body");
    const selected = normaliseRecordTab(tab);
    if (selected === "Journey") await renderAfterWeddingV846(record, body);
    if (selected === "Overview") await renderAfterWeddingOverviewV846(record, body);
  };

  window.WBMAfterWeddingV846 = Object.freeze({
    version: "8.46",
    statuses: ["photos", "video", "album", "review-request", "completion"],
  });
})();
