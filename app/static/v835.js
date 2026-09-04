/* V8.35 — private holiday and manual date blocks. */
(() => {
  const baseRenderCalendarV835 = renderCalendar;
  let calendarRenderSequence = 0;

  function londonToday() {
    try {
      return new Intl.DateTimeFormat("en-CA", {
        timeZone: "Europe/London", year: "numeric", month: "2-digit", day: "2-digit"
      }).format(new Date());
    } catch (_) {
      return new Date().toISOString().slice(0, 10);
    }
  }

  function dateBlockRange(block) {
    if (block.start_date === block.end_date) return fmtDate(block.start_date);
    return `${fmtDate(block.start_date)} – ${fmtDate(block.end_date)}`;
  }

  function calendarStatus(block) {
    const status = block.calendar_status || "pending";
    if (status === "synced") return `<span class="v835-calendar-state synced">✓ Google Calendar synced</span>`;
    if (status === "removed") return `<span class="v835-calendar-state synced">✓ Google Calendar removed</span>`;
    const label = status === "error" ? "Google Calendar needs attention" : "Google Calendar pending";
    return `<span class="v835-calendar-state attention">! ${esc(label)}</span>`;
  }

  function dateBlockCard(block) {
    return `<article class="v835-block-card" data-date-block="${attr(block.id)}">
      <div class="v835-block-icon">☀</div>
      <div class="v835-block-main">
        <small>DATES BLOCKED · PRIVATE</small>
        <strong>${esc(block.label)}</strong>
        <span>${esc(dateBlockRange(block))}</span>
        ${block.notes ? `<p>${esc(block.notes)}</p>` : ""}
        ${calendarStatus(block)}
        ${block.calendar_error ? `<em>${esc(block.calendar_error)}</em>` : ""}
      </div>
      <div class="v835-block-actions">
        ${block.calendar_link ? `<a class="mini" href="${attr(block.calendar_link)}" target="_blank" rel="noopener">Open calendar</a>` : ""}
        ${["error", "pending", "pending_delete"].includes(block.calendar_status) ? `<button type="button" class="mini" data-v835-retry>Retry calendar</button>` : ""}
        <button type="button" class="mini" data-v835-edit>Edit</button>
        <button type="button" class="mini danger-text" data-v835-delete>Remove</button>
      </div>
    </article>`;
  }

  function blockPanel(blocks, loadError = "") {
    return `<section class="panel v835-block-panel">
      <div class="v835-block-heading">
        <div><small>WEDDINGS BY MARK AVAILABILITY</small><h2>Holidays & blocked dates</h2><p>These dates show as <strong>Booked</strong> on your website and stay private from couples.</p></div>
        <button type="button" class="primary" id="v835-add-block">＋ Block dates / holiday</button>
      </div>
      <div class="v835-safety-strip"><i>✓</i><span><strong>No client emails or invoices</strong><small>One private all-day Google Calendar event is kept in step with each block.</small></span></div>
      ${loadError ? `<p class="error v835-load-error">${esc(loadError)}</p>` : ""}
      <div class="v835-block-list">${blocks.length ? blocks.map(dateBlockCard).join("") : `<div class="v835-no-blocks"><strong>No dates manually blocked</strong><span>Use the button above for a holiday, day off or any period you are unavailable.</span></div>`}</div>
    </section>`;
  }

  async function checkBlockDates(startDate, endDate, block = null) {
    const query = new URLSearchParams({ start_date: startDate, end_date: endDate });
    if (block) query.set("exclude_id", block.id);
    const check = await api(`/api/date-blocks/check?${query}`);
    if (check.existing_block) {
      const existing = check.existing_block;
      throw new Error(`These dates overlap “${existing.label}” (${dateBlockRange(existing)}). Edit that block instead.`);
    }
    if (!check.booking_conflict_count) return false;
    const preview = check.booking_conflicts.slice(0, 4)
      .map(item => `${fmtDate(item.date)} — ${item.title}`).join("\n");
    return window.confirm(
      `This period contains ${check.booking_conflict_count} existing wedding or enquiry record${check.booking_conflict_count === 1 ? "" : "s"}:\n\n${preview}${check.booking_conflict_count > 4 ? "\n…" : ""}\n\nThe records will stay unchanged. Block these dates anyway?`
    );
  }

  function openDateBlockModal(block = null) {
    const start = block?.start_date || londonToday();
    const end = block?.end_date || start;
    showModal(
      block ? "Edit blocked dates" : "Block dates / holiday",
      `<div class="full v835-modal-note"><i>☀</i><span><strong>Choose one day or a complete date range</strong><small>The end date is included. The private label and notes never appear on your website.</small></span></div>
       <label>First blocked date<input id="v835-start" type="date" value="${attr(start)}" required></label>
       <label>Last blocked date<input id="v835-end" type="date" value="${attr(end)}" required></label>
       <label class="full">Private label<input id="v835-label" maxlength="160" value="${attr(block?.label || "Holiday")}" placeholder="Holiday" required><small class="field-help">Visible only here and on your own Google Calendar.</small></label>
       <label class="full">Private notes (optional)<textarea id="v835-notes" maxlength="2000" rows="3" placeholder="For example: Away in Cornwall">${esc(block?.notes || "")}</textarea></label>
       <div class="full v835-no-email"><strong>🔒 No email will be sent to any couple.</strong></div>`,
      async () => {
        const startDate = value("#v835-start");
        const endDate = value("#v835-end");
        if (endDate < startDate) throw new Error("The last blocked date must be on or after the first date.");
        const confirmed = await checkBlockDates(startDate, endDate, block);
        const checkAgain = await api(`/api/date-blocks/check?${new URLSearchParams({
          start_date: startDate, end_date: endDate, ...(block ? { exclude_id: block.id } : {})
        })}`);
        if (checkAgain.booking_conflict_count && !confirmed) {
          throw new Error("The blocked period was not saved. Review the existing records and try again when ready.");
        }
        const payload = {
          start_date: startDate,
          end_date: endDate,
          label: value("#v835-label").trim(),
          notes: nullable(value("#v835-notes")),
          confirm_conflicts: Boolean(checkAgain.booking_conflict_count && confirmed)
        };
        await api(block ? `/api/date-blocks/${block.id}` : "/api/date-blocks", {
          method: block ? "PUT" : "POST", body: JSON.stringify(payload)
        });
        closeModal();
        toast(block ? "Blocked dates updated · no email sent" : "Dates blocked · website and calendar updated");
        renderCalendar();
      },
      block ? "Update the unavailable period safely." : "Reserve time away without creating a fake booking."
    );
    const startInput = $("#v835-start");
    const endInput = $("#v835-end");
    startInput.onchange = () => {
      if (!endInput.value || endInput.value < startInput.value) endInput.value = startInput.value;
      endInput.min = startInput.value;
    };
    endInput.min = startInput.value;
  }

  function wireDateBlocks(blocks) {
    $("#v835-add-block")?.addEventListener("click", () => openDateBlockModal());
    $$("[data-date-block]").forEach(card => {
      const block = blocks.find(item => item.id === card.dataset.dateBlock);
      card.querySelector("[data-v835-edit]")?.addEventListener("click", () => openDateBlockModal(block));
      card.querySelector("[data-v835-delete]")?.addEventListener("click", async () => {
        if (!window.confirm(`Remove “${block.label}” (${dateBlockRange(block)})?\n\nThe website dates will become available again unless a real wedding protects them. No client email will be sent.`)) return;
        try {
          const result = await api(`/api/date-blocks/${block.id}`, { method: "DELETE" });
          toast(result.message || "Blocked period removed");
          renderCalendar();
        } catch (error) {
          toast(error.message, "error");
        }
      });
      card.querySelector("[data-v835-retry]")?.addEventListener("click", async () => {
        try {
          const result = await api(`/api/date-blocks/${block.id}/google-calendar-sync`, { method: "POST" });
          toast(result.status === "synced" ? "Google Calendar synced" : (result.last_error || "Calendar retry saved"));
          renderCalendar();
        } catch (error) {
          toast(error.message, "error");
        }
      });
    });
  }

  renderCalendar = async function () {
    const sequence = ++calendarRenderSequence;
    $("#content").innerHTML = `<div class="panel loading">Loading calendar and blocked dates…</div>`;
    let blocks = [];
    let loadError = "";
    try {
      blocks = await api("/api/date-blocks");
    } catch (error) {
      loadError = `Blocked dates could not be loaded: ${error.message}`;
    }
    if (sequence !== calendarRenderSequence || state.view !== "calendar") return;
    baseRenderCalendarV835();
    const content = $("#content");
    content.insertAdjacentHTML("afterbegin", blockPanel(blocks, loadError));
    wireDateBlocks(blocks);
  };

  const baseSameDateConflictDataV835 = sameDateConflictData;
  sameDateConflictData = function (record) {
    const result = baseSameDateConflictDataV835(record);
    result.blocked = Number(record.same_date_conflict?.blocked_dates || 0);
    result.manuallyBlocked = Boolean(record.same_date_conflict?.is_manually_blocked || result.blocked);
    return result;
  };

  const baseSameDateConflictTextV835 = sameDateConflictText;
  sameDateConflictText = function (record) {
    const conflict = sameDateConflictData(record);
    if (conflict.manuallyBlocked) {
      const enquiry = ["enquiry", "quoted"].includes(record.status);
      return {
        label: "DATE BLOCKED",
        detail: enquiry
          ? `This enquiry falls on a manually blocked date (${fmtDate(record.event_date)}). Review it before sending a quote.`
          : `This wedding falls on a manually blocked date (${fmtDate(record.event_date)}). Review the holiday/date block in Calendar.`
      };
    }
    return baseSameDateConflictTextV835(record);
  };

  sameDateConflictBanner = function (record) {
    const warning = sameDateConflictText(record);
    if (!warning) return "";
    const heading = sameDateConflictData(record).manuallyBlocked ? "DATE BLOCK WARNING" : "DATE CLASH WARNING";
    return `<section class="same-date-conflict-banner" role="alert"><i>!</i><div><small>${heading}</small><strong>${esc(warning.label)}</strong><span>${esc(warning.detail)}</span></div></section>`;
  };
})();
