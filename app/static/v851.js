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

  function customSchedule(workflow) {
    return `${workflow.days} day${workflow.days === 1 ? '' : 's'} ${workflow.direction} ${workflow.trigger_label}`;
  }

  function customWorkflowRows(data) {
    if (!data.custom_workflows.length) return `<div class="v852-custom-empty"><strong>No custom workflows yet</strong><span>Create your own client journey without changing the protected built-in workflows below.</span><button class="primary" data-v852-add>＋ Add your first workflow</button></div>`;
    return `<div class="v852-custom-list">${data.custom_workflows.map(workflow => `<article class="v852-custom-row ${attr(workflow.status)}" data-custom-workflow="${attr(workflow.id)}">
      <div class="v852-custom-main"><span class="v852-status ${attr(workflow.status)}">${esc(workflow.status)}</span><strong>${esc(workflow.name)}</strong><small>${esc(customSchedule(workflow))} · ${esc(modeLabels[workflow.mode][0])}</small><small>Template: ${esc(workflow.template_name)}${workflow.template_available ? '' : ' · unavailable'}</small></div>
      <div class="v852-custom-actions">
        <button class="mini" data-v852-preview="${attr(workflow.id)}">Preview &amp; test</button>
        ${workflow.status === 'active' ? `<button class="mini" data-v852-pause="${attr(workflow.id)}">Pause</button>` : `<button class="mini" data-v852-edit="${attr(workflow.id)}">Edit</button><button class="primary" data-v852-activate="${attr(workflow.id)}">Activate</button>`}
        <button class="mini" data-v852-duplicate="${attr(workflow.id)}">Duplicate</button>
        ${workflow.status === 'active' ? '' : `<button class="mini danger-text" data-v852-delete="${attr(workflow.id)}">Delete</button>`}
      </div>
    </article>`).join('')}</div>`;
  }

  function workflowPanel(data) {
    const counts = data.rules.reduce((result, rule) => ({...result, [rule.mode]: (result[rule.mode] || 0) + 1}), {});
    return `<section class="panel v851-studio">
      <header class="v851-hero"><div><small>V8.51 · WEDDINGS BY MARK</small><h2>Custom Workflow Studio</h2><p>Choose what happens, when it happens, and whether an email needs your approval.</p></div>
        <span class="v851-live ${data.reminders_enabled ? "on" : "off"}">${data.reminders_enabled ? "AUTOMATION LIVE" : "AUTOMATION PAUSED"}</span></header>
      <div class="v851-summary"><span><b>${counts.automatic || 0}</b> automatic</span><span><b>${counts.review || 0}</b> review first</span><span><b>${counts.task || 0}</b> task only</span><span><b>${counts.off || 0}</b> off</span><span class="v851-window">Checks every ${data.scan_hours} hour${data.scan_hours === 1 ? "" : "s"} · ${esc(data.delivery_window)}</span></div>
      <div class="v851-layout"><div class="v851-editor">
        <div class="v851-safety"><strong>Your existing setup is preserved</strong><span>Nothing changed automatically during this update. Adjust a workflow only when you want to.</span></div>
        <section class="v852-custom"><header><div><small>YOUR WORKFLOW BUILDER</small><h3>Custom workflows</h3><p>Build extra steps as drafts, test them, then activate when ready.</p></div><button class="primary" data-v852-add>＋ Add workflow</button></header>${customWorkflowRows(data)}</section>
        <div class="v852-protected-title"><span>PROTECTED BUILT-IN WORKFLOWS</span><small>These proven journeys stay editable but cannot be deleted.</small></div>
        ${groupedRules(data.rules)}
        <footer class="v851-savebar"><span>Changes affect future workflow checks, not emails already sent.</span><button id="v851-save" class="primary">Save workflow changes</button></footer>
      </div><aside class="v851-side">
        <section><header><div><small>APPROVAL QUEUE</small><h3>Waiting for you</h3></div><b>${data.pending_review.length}</b></header>${reviewRows(data.pending_review)}</section>
        <section><header><div><small>LIVE PREVIEW</small><h3>Coming up</h3></div></header>${upcomingRows(data.upcoming)}</section>
      </aside></div>
    </section>`;
  }

  function workflowTemplateOptions(data, selected) {
    return data.available_templates.map(template => `<option value="${attr(template.template_key)}" ${selected === template.template_key ? 'selected' : ''}>${esc(template.display_name)}</option>`).join('') + `<option value="__new__">＋ Create a new email template</option>`;
  }

  function customWorkflowFields(data, workflow = null) {
    const selectedTrigger = workflow?.trigger || data.triggers[0].key;
    const selectedDirection = workflow?.direction || data.triggers.find(item => item.key === selectedTrigger).directions[0];
    return `<label class="full">Workflow name<input id="v852-name" maxlength="140" value="${attr(workflow?.name || '')}" placeholder="Example: One-week planning check-in" required></label>
      <label>Starts from<select id="v852-trigger">${data.triggers.map(trigger => `<option value="${attr(trigger.key)}" ${selectedTrigger === trigger.key ? 'selected' : ''}>${esc(trigger.label)}</option>`).join('')}</select></label>
      <label>When<select id="v852-direction">${data.triggers.find(item => item.key === selectedTrigger).directions.map(direction => `<option value="${direction}" ${selectedDirection === direction ? 'selected' : ''}>${direction}</option>`).join('')}</select></label>
      <label>Number of days<input id="v852-days" type="number" min="0" max="365" value="${workflow?.days ?? 1}" required></label>
      <label>Action<select id="v852-mode"><option value="automatic" ${workflow?.mode === 'automatic' ? 'selected' : ''}>Automatic</option><option value="review" ${!workflow || workflow?.mode === 'review' ? 'selected' : ''}>Review first</option><option value="task" ${workflow?.mode === 'task' ? 'selected' : ''}>Task only</option></select></label>
      <label class="full">Email template<select id="v852-template">${workflowTemplateOptions(data, workflow?.template_key || data.available_templates[0]?.template_key || '__new__')}</select><small class="field-help">Review first is the safest choice while proof-testing a new journey.</small></label>
      <div id="v852-new-template" class="full v852-new-template hidden"><div class="section-label">NEW EMAIL TEMPLATE</div><label>Template name<input id="v852-template-name" maxlength="140"></label><label>Subject<input id="v852-template-subject" maxlength="240" placeholder="Hello {client_first_name}"></label><label class="full">Email body<textarea id="v852-template-body" rows="10" placeholder="Hi {client_first_name},&#10;&#10;Write your message here…&#10;&#10;[OPEN YOUR ACCOUNT]({portal_url})"></textarea><small class="field-help">Client names, dates and the secure account link are inserted when sent.</small></label></div>`;
  }

  function wireCustomEditor(data) {
    const trigger = $('#v852-trigger'), direction = $('#v852-direction'), template = $('#v852-template');
    trigger.onchange = () => {
      const choices = data.triggers.find(item => item.key === trigger.value).directions;
      direction.innerHTML = choices.map(value => `<option value="${value}">${value}</option>`).join('');
    };
    const showNew = () => {
      const block = $('#v852-new-template');
      block.classList.toggle('hidden', template.value !== '__new__');
      ['#v852-template-name', '#v852-template-subject', '#v852-template-body'].forEach(selector => $(selector).required = template.value === '__new__');
    };
    template.onchange = showNew; showNew();
  }

  async function saveCustomWorkflow(data, workflow) {
    let templateKey = value('#v852-template');
    if (templateKey === '__new__') {
      const workflowName = value('#v852-name').trim();
      templateKey = `custom_${catalogCode(workflowName).slice(0, 45)}_${Date.now().toString(36)}`.slice(0, 80);
      await api('/api/communications/templates', {method: 'POST', body: JSON.stringify({
        brand: 'wbm', template_key: templateKey,
        display_name: value('#v852-template-name').trim(),
        subject: value('#v852-template-subject').trim(),
        body: value('#v852-template-body').trim(), is_active: true,
      })});
    }
    const payload = {name: value('#v852-name').trim(), trigger: value('#v852-trigger'),
      direction: value('#v852-direction'), days: Number(value('#v852-days')),
      mode: value('#v852-mode'), template_key: templateKey};
    await api(workflow ? `/api/communications/workflows/custom/${workflow.id}` : '/api/communications/workflows/custom', {
      method: workflow ? 'PUT' : 'POST', body: JSON.stringify(payload),
    });
    closeModal(); toast(workflow ? 'Workflow draft updated' : 'Workflow created safely as a draft'); renderCommunicationsV2();
  }

  function openCustomWorkflowEditor(data, workflow = null) {
    showModal(workflow ? `Edit ${workflow.name}` : 'Add custom workflow', customWorkflowFields(data, workflow),
      () => saveCustomWorkflow(data, workflow),
      'Nothing will run yet. New and edited workflows remain drafts until you deliberately activate them.');
    wireCustomEditor(data);
  }

  function activateCustomWorkflow(workflow) {
    showModal(`Activate ${workflow.name}`, `<div class="full v852-activation-warning"><strong>Who should enter this workflow?</strong><p>The safe choice affects only bookings created after activation. Existing couples will not suddenly receive an old step.</p></div>
      <label class="full check-option"><input type="radio" name="v852-scope" value="future" checked><span><strong>New bookings only</strong><small>Recommended while proof-testing.</small></span></label>
      <label class="full check-option warning"><input type="radio" name="v852-scope" value="existing"><span><strong>Include current eligible bookings</strong><small>May prepare or send a step that is already due. Choose only deliberately.</small></span></label>`, async () => {
        const includeExisting = document.querySelector('input[name="v852-scope"]:checked').value === 'existing';
        if (includeExisting && !confirm('Include current eligible bookings as well? This may make a workflow due immediately.')) return;
        await api(`/api/communications/workflows/custom/${workflow.id}/activate`, {method: 'POST', body: JSON.stringify({include_existing: includeExisting})});
        closeModal(); toast('Custom workflow activated'); renderCommunicationsV2();
      }, 'Activation does not itself send anything; the normal daytime workflow check applies.');
  }

  async function customWorkflowAction(data, id, action) {
    const workflow = data.custom_workflows.find(item => item.id === id);
    if (!workflow) return;
    if (action === 'edit') return openCustomWorkflowEditor(data, workflow);
    if (action === 'activate') return activateCustomWorkflow(workflow);
    if (action === 'preview') {
      const template = data.available_templates.find(item => item.template_key === workflow.template_key);
      return template ? previewEmailTemplate(template) : toast('This email template is unavailable', 'error');
    }
    if (action === 'pause') {
      if (!confirm(`Pause “${workflow.name}”?\n\nNo new couples will enter it until you reactivate it.`)) return;
      await api(`/api/communications/workflows/custom/${id}/pause`, {method: 'POST'}); toast('Workflow paused');
    } else if (action === 'duplicate') {
      await api(`/api/communications/workflows/custom/${id}/duplicate`, {method: 'POST'}); toast('Draft copy created');
    } else if (action === 'delete') {
      if (!confirm(`Delete the draft “${workflow.name}”?\n\nSent email history is never deleted.`)) return;
      await api(`/api/communications/workflows/custom/${id}`, {method: 'DELETE'}); toast('Workflow deleted');
    }
    renderCommunicationsV2();
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
      $$('[data-v852-add]', studio).forEach(button => button.onclick = () => openCustomWorkflowEditor(data));
      const customActions = {preview: '[data-v852-preview]', edit: '[data-v852-edit]', activate: '[data-v852-activate]', pause: '[data-v852-pause]', duplicate: '[data-v852-duplicate]', delete: '[data-v852-delete]'};
      Object.entries(customActions).forEach(([action, selector]) => $$(selector, studio).forEach(button => button.onclick = async () => {
        button.disabled = true;
        try { await customWorkflowAction(data, button.dataset[`v852${action[0].toUpperCase()}${action.slice(1)}`], action); }
        catch (error) { button.disabled = false; toast(error.message, 'error'); }
      }));
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
