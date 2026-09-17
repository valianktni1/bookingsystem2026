/* V8.51 Custom Workflow Studio */
(() => {
  const modeLabels = {
    automatic: ["Automatic", "Sends without waiting for you"],
    review: ["Review first", "Waits for your approval"],
    task: ["Task only", "Reminds you; sends nothing"],
    off: ["Off", "No email and no task"],
  };

  function modeOptions(selected) {
    return Object.entries(modeLabels).map(([key, value]) =>
      `<option value="${key}" ${selected === key ? "selected" : ""}>${value[0]}</option>`
    ).join("");
  }

  function ruleRow(rule) {
    const repeat = rule.repeatable
      ? `<label class="v851-repeat">Repeat every <input data-workflow-repeat type="number" min="1" max="60" value="${rule.repeat_days}"> days while unpaid</label>`
      : "";
    return `<article class="v851-rule" data-workflow-key="${attr(rule.key)}">
      <div class="v851-rule-copy"><strong>${esc(rule.label)}</strong><span>${esc(rule.description)}</span></div>
      <label class="v851-mode"><span>Action</span><select data-workflow-mode>${modeOptions(rule.mode)}</select><small data-mode-help>${esc(modeLabels[rule.mode][1])}</small></label>
      <label class="v851-timing"><span>Timing</span><b><input data-workflow-days type="number" min="0" max="365" value="${rule.days}"> days ${esc(rule.direction)} ${esc(rule.anchor_label)}</b>${repeat}</label>
    </article>`;
  }

  function groupedRules(rules) {
    const groups = new Map();
    rules.forEach(rule => {
      if (!groups.has(rule.group)) groups.set(rule.group, []);
      groups.get(rule.group).push(rule);
    });
    return [...groups].map(([group, rows], index) => `<details class="v851-group" ${index < 2 ? "open" : ""}>
      <summary><span>${esc(group)}</span><b>${rows.length} workflow${rows.length === 1 ? "" : "s"}</b></summary>
      <div>${rows.map(ruleRow).join("")}</div>
    </details>`).join("");
  }

  function reviewRows(rows) {
    if (!rows.length) return `<div class="v851-empty"><strong>Nothing waiting for approval</strong><span>Review-first emails will appear here before anything is sent.</span></div>`;
    return rows.map(row => `<article class="v851-queue-row">
      <span><strong>${esc(row.booking_title)}</strong><small>${esc(row.label)} · due ${esc(fmtDate(row.scheduled_for))}</small></span>
      <button class="primary" data-workflow-review="${attr(row.id)}">Review email</button>
    </article>`).join("");
  }

  function upcomingRows(rows) {
    if (!rows.length) return `<div class="v851-empty"><strong>No emails scheduled in the next 180 days</strong><span>Off workflows are deliberately excluded.</span></div>`;
    return rows.slice(0, 12).map(row => `<button class="v851-upcoming-row" data-record="${attr(row.booking_id)}">
      <time>${esc(fmtDate(row.scheduled_for))}</time><span><strong>${esc(row.booking_title)}</strong><small>${esc(row.label)}</small></span><i class="v851-mode-pill ${attr(row.mode)}">${esc(modeLabels[row.mode][0])}</i>
    </button>`).join("");
  }

  function workflowPanel(data) {
    const counts = data.rules.reduce((result, rule) => ({...result, [rule.mode]: (result[rule.mode] || 0) + 1}), {});
    return `<section class="panel v851-studio">
      <header class="v851-hero"><div><small>V8.51 · WEDDINGS BY MARK</small><h2>Custom Workflow Studio</h2><p>Choose what happens, when it happens, and whether an email needs your approval.</p></div>
        <span class="v851-live ${data.reminders_enabled ? "on" : "off"}">${data.reminders_enabled ? "AUTOMATION LIVE" : "AUTOMATION PAUSED"}</span></header>
      <div class="v851-summary"><span><b>${counts.automatic || 0}</b> automatic</span><span><b>${counts.review || 0}</b> review first</span><span><b>${counts.task || 0}</b> task only</span><span><b>${counts.off || 0}</b> off</span><span class="v851-window">Checks every ${data.scan_hours} hour${data.scan_hours === 1 ? "" : "s"} · ${esc(data.delivery_window)}</span></div>
      <div class="v851-layout"><div class="v851-editor">
        <div class="v851-safety"><strong>Your existing setup is preserved</strong><span>Nothing changed automatically during this update. Adjust a workflow only when you want to.</span></div>
        ${groupedRules(data.rules)}
        <footer class="v851-savebar"><span>Changes affect future workflow checks, not emails already sent.</span><button id="v851-save" class="primary">Save workflow changes</button></footer>
      </div><aside class="v851-side">
        <section><header><div><small>APPROVAL QUEUE</small><h3>Waiting for you</h3></div><b>${data.pending_review.length}</b></header>${reviewRows(data.pending_review)}</section>
        <section><header><div><small>LIVE PREVIEW</small><h3>Coming up</h3></div></header>${upcomingRows(data.upcoming)}</section>
      </aside></div>
    </section>`;
  }

  function collectRules(root) {
    const rules = {};
    $$('[data-workflow-key]', root).forEach(row => {
      const repeat = $('[data-workflow-repeat]', row);
      rules[row.dataset.workflowKey] = {
        mode: $('[data-workflow-mode]', row).value,
        days: Number($('[data-workflow-days]', row).value),
        ...(repeat ? {repeat_days: Number(repeat.value)} : {}),
      };
    });
    return rules;
  }

  async function saveWorkflows(root) {
    const button = $('#v851-save', root);
    button.disabled = true;
    button.textContent = "Saving…";
    try {
      await api('/api/communications/workflows', {method: 'PUT', body: JSON.stringify({rules: collectRules(root)})});
      toast('Workflow choices saved');
      renderCommunicationsV2();
    } catch (error) {
      button.disabled = false;
      button.textContent = "Save workflow changes";
      toast(error.message, 'error');
    }
  }

  async function showReview(reminderId) {
    try {
      const preview = await api(`/api/communications/workflows/review/${reminderId}/preview`);
      const content = $('#modal-content');
      content.innerHTML = `<div class="modal-head"><div><small>REVIEW FIRST · NOTHING SENT YET</small><h2>${esc(preview.booking_title)}</h2><p>${esc(preview.subject)}</p></div><button type="button" id="close-modal">×</button></div>
        <div class="v851-review-body"><iframe id="v851-review-frame" class="email-preview-frame" title="Email preview"></iframe></div>
        <footer class="v851-review-actions"><button id="v851-review-skip" class="secondary">Skip this email</button><button id="v851-review-send" class="primary">Approve and send</button></footer>`;
      $('#modal').classList.remove('hidden'); $('#modal-overlay').classList.remove('hidden');
      $('#close-modal').onclick = closeModal;
      $('#v851-review-frame').srcdoc = preview.html;
      $('#v851-review-skip').onclick = async () => {
        if (!confirm('Skip this workflow email? Nothing will be sent to the couple.')) return;
        await api(`/api/communications/workflows/review/${reminderId}/skip`, {method: 'POST'});
        closeModal(); toast('Workflow email skipped'); renderCommunicationsV2();
      };
      $('#v851-review-send').onclick = async event => {
        const button = event.currentTarget; button.disabled = true; button.textContent = 'Sending…';
        try {
          await api(`/api/communications/workflows/review/${reminderId}/send`, {method: 'POST'});
          closeModal(); toast('Workflow email sent'); renderCommunicationsV2();
        } catch (error) { button.disabled = false; button.textContent = 'Approve and send'; toast(error.message, 'error'); }
      };
    } catch (error) { toast(error.message, 'error'); }
  }

  async function appendWorkflowStudio() {
    const content = $('#content');
    if (!content || state.view !== 'communications' || state.brand === 'ivory' || $('.v851-studio', content)) return;
    try {
      const data = await api('/api/communications/workflows');
      if (state.view !== 'communications') return;
      content.insertAdjacentHTML('afterbegin', workflowPanel(data));
      const studio = $('.v851-studio', content);
      $$('[data-workflow-mode]', studio).forEach(select => select.onchange = () => {
        $('[data-mode-help]', select.closest('[data-workflow-key]')).textContent = modeLabels[select.value][1];
        select.closest('[data-workflow-key]').dataset.mode = select.value;
      });
      $('#v851-save', studio).onclick = () => saveWorkflows(studio);
      $$('[data-workflow-review]', studio).forEach(button => button.onclick = () => showReview(button.dataset.workflowReview));
      const runButton = $('#run-reminders', content);
      if (runButton) runButton.onclick = async () => {
        runButton.disabled = true;
        try {
          const result = await api('/api/communications/reminders/run', {method: 'POST'});
          const extras = [
            result.awaiting_review ? `${result.awaiting_review} awaiting review` : '',
            result.tasks_created ? `${result.tasks_created} task${result.tasks_created === 1 ? '' : 's'} created` : '',
          ].filter(Boolean).join(', ');
          toast(`Workflow check: ${result.sent} sent, ${result.failed} failed${extras ? `, ${extras}` : ''}`);
          renderCommunicationsV2();
        } catch (error) { runButton.disabled = false; toast(error.message, 'error'); }
      };
      wireRecords(studio);
    } catch (error) {
      content.insertAdjacentHTML('afterbegin', `<section class="panel v851-studio"><div class="empty"><strong>Workflow Studio unavailable</strong>${esc(error.message)}</div></section>`);
    }
  }

  const baseRenderCommunicationsV851 = renderCommunicationsV2;
  renderCommunicationsV2 = async function () {
    await baseRenderCommunicationsV851();
    await appendWorkflowStudio();
  };
})();
