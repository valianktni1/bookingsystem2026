/* V8.74 - concise, mobile-first Final Wedding Timings review. */
(() => {
  const baseRenderQuestionnaires = renderQuestionnaires;
  const internalKeys = new Set([
    "_calculation",
    "_form_template",
    "_answer_snapshot",
    "_template_revision",
    "source_questionnaire_text",
    "submission_source",
    "venue_place_id",
    "venue_lat",
    "venue_lng",
  ]);

  const fallbackLabels = {
    ceremony_time: "Ceremony time",
    ceremony_duration: "Expected ceremony length",
    ceremony_venue: "Ceremony venue and address",
    reception_same: "Reception at the same venue",
    reception_venue: "Reception venue and address",
    prep_photos: "Preparation photographs",
    prep_person: "Who is getting ready",
    prep_venue: "Preparation venue and address",
    travel_minutes: "Travel to ceremony",
    start_choice: "Preferred photography start",
    requested_start: "Requested earlier start",
    prep_notes: "Preparation notes",
    second_prep: "Second preparation location",
    group_photo_time: "Group photograph time",
    meal_time: "Wedding breakfast / meal time",
    speeches_time: "Speeches time",
    speeches_position: "When speeches take place",
    evening_time: "Evening guests arrive",
    cake_time: "Cake cutting",
    first_dance_time: "First dance",
    later_event: "Essential event after first dance",
    later_event_name: "Later event",
    later_event_time: "Later event time",
    extra_stops: "Additional stops or venues",
    day_contact: "Wedding-day contact",
    day_mobile: "Wedding-day mobile",
    coordinator: "Coordinator / venue contact",
    group_count: "Formal group photographs",
    important_notes: "Important notes",
  };

  function durationText(minutes) {
    if (minutes === null || minutes === undefined || Number.isNaN(Number(minutes))) return "Check";
    const value = Math.max(0, Number(minutes));
    const hours = Math.floor(value / 60);
    const mins = value % 60;
    if (!hours) return `${mins} min`;
    return mins ? `${hours} hr ${mins} min` : `${hours} hr`;
  }

  function answerValue(value) {
    if (value === true) return "Yes";
    if (value === false) return "No";
    if (value === null || value === undefined || String(value).trim() === "") return "Not answered";
    return String(value);
  }

  function answerRows(values) {
    const snapshot = Array.isArray(values._answer_snapshot) ? values._answer_snapshot : [];
    const rows = snapshot.length
      ? snapshot
          .filter(item => item && !internalKeys.has(item.key))
          .map(item => [item.key, item.label || fallbackLabels[item.key] || questionnaireLabel(item.key),
            values[item.key] ?? item.answer])
      : Object.entries(values)
          .filter(([key]) => !internalKeys.has(key))
          .map(([key, value]) => [key, fallbackLabels[key] || questionnaireLabel(key), value]);
    return rows.map(([, label, value]) =>
      `<div><dt>${esc(label)}</dt><dd>${esc(answerValue(value)).replace(/\n/g, "<br>")}</dd></div>`
    ).join("");
  }

  function timingCard(r, submission) {
    const values = submission.data || {};
    const calc = values._calculation || {};
    const timeline = Array.isArray(calc.timeline) ? calc.timeline : [];
    const status = calc.status === "over"
      ? `Over by ${durationText(calc.over_standard_minutes)}`
      : calc.status === "within_grace"
        ? "Within 15-minute grace"
        : calc.status === "package_review"
          ? "Package needs checking"
          : "Fits included coverage";
    const reviewed = state.currentPortal?.final_timings?.reviewed_at;
    const timelineHtml = timeline.length
      ? timeline.map(item => `<div><b>${esc(item.time || "")}</b><span><strong>${esc(item.event || "")}</strong><small>${esc(item.detail || "")}</small></span></div>`).join("")
      : '<p class="muted">No calculated timeline is available for this older submission.</p>';
    const contact = [values.day_contact, values.day_mobile].filter(Boolean).join(" · ") || "Not supplied";
    const keyDetails = [
      ["Wedding-day contact", contact],
      ["Coordinator", answerValue(values.coordinator)],
      ["Formal groups", answerValue(values.group_count)],
      ["Important notes", answerValue(values.important_notes)],
      ["Preparation notes", answerValue(values.prep_notes)],
      ["Extra stops", answerValue(values.extra_stops)],
    ];
    const keyDetailsHtml = keyDetails.map(([label, value]) =>
      `<div><dt>${esc(label)}</dt><dd>${esc(value).replace(/\n/g, "<br>")}</dd></div>`
    ).join("");
    const warning = calc.coverage_warning
      ? `<div class="v874-warning"><strong>Coverage needs attention</strong><span>These timings exceed the included coverage by ${durationText(calc.over_standard_minutes)}. The calculation suggests ${Number(calc.additional_hours_suggested || 0)} additional hour${Number(calc.additional_hours_suggested || 0) === 1 ? "" : "s"}.</span></div>`
      : calc.travel_warning
        ? '<div class="v874-warning"><strong>Preparation travel needs checking</strong><span>The preparation window may be tight once travel and the ceremony-arrival buffer are included.</span></div>'
        : "";
    const technical = Object.keys(calc).length
      ? `<details class="v874-technical"><summary>Technical calculation details</summary><p>Only needed for troubleshooting. These are the app’s background workings, not extra answers from the couple.</p><pre>${esc(JSON.stringify(calc, null, 2))}</pre></details>`
      : "";

    return `<article class="questionnaire-card v874-final-timings">
      <header><div><small>BOOKINGSYSTEM2026 · FINAL TIMINGS</small><h3>Wedding-day run sheet</h3><span>Submitted ${esc(fmtDateTime(submission.submitted_at))}${reviewed ? ` · Reviewed ${esc(fmtDateTime(reviewed))}` : ""}</span></div><b>${esc(status)}</b></header>
      <section class="v874-summary" aria-label="Overall timings">
        <article><small>SUGGESTED START</small><strong>${esc(calc.suggested_start || "Check")}</strong></article>
        <article><small>CEREMONY</small><strong>${esc(values.ceremony_time || "Check")}</strong></article>
        <article><small>EXPECTED FINISH</small><strong>${esc(calc.expected_finish || values.first_dance_time || "Check")}</strong></article>
        <article><small>TOTAL COVERAGE</small><strong>${durationText(calc.coverage_minutes)}</strong></article>
      </section>
      ${warning}
      <div class="v874-review-grid">
        <section><h4>Timeline</h4><div class="v874-timeline">${timelineHtml}</div></section>
        <section><h4>Contacts & important notes</h4><dl>${keyDetailsHtml}</dl></section>
      </div>
      <div class="v874-review-actions"><a class="primary" href="/api/bookings/${attr(r.id)}/final-timings.pdf" target="_blank" rel="noopener">View / download PDF</a></div>
      <details class="v874-all-answers"><summary>View every answer from the couple</summary><dl>${answerRows(values)}</dl></details>
      ${technical}
    </article>`;
  }

  renderQuestionnaires = function renderQuestionnairesV874(r, body) {
    baseRenderQuestionnaires(r, body);
    const submissions = state.currentPortal?.submissions || [];
    const cards = [...body.querySelectorAll(".questionnaire-card")];
    submissions.forEach((submission, index) => {
      if (submission.form_type === "final_timings" && cards[index]) {
        cards[index].outerHTML = timingCard(r, submission);
      }
    });
  };
})();
