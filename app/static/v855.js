/* V8.55: presentation helpers. No API calls, writes, or automation changes. */
(() => {
  'use strict';
  const eligible = record => record?.brand === 'wbm' && record?.kind === 'wedding' && !record.legacy_source;

  function fold(node, title, status, open = false) {
    if (!node || node.parentElement?.classList.contains('v855-fold')) return null;
    const box = document.createElement('details');
    box.className = 'v855-fold';
    box.open = open;
    const summary = document.createElement('summary');
    const name = document.createElement('strong');
    name.textContent = title;
    const label = document.createElement('span');
    label.textContent = status;
    summary.append(name, label);
    node.before(box);
    box.append(summary, node); // Move existing nodes: keep every bound handler.
    return box;
  }

  function rememberPanel(record, box, title, status) {
    if (!box || !record.id) return;
    // Status is part of the key: newly outstanding work gets its default visibility.
    const key = `wbm-panel:${record.id}:${title}:${status}`;
    try {
      const value = sessionStorage.getItem(key);
      if (value !== null) box.open = value === 'open';
    } catch (_) { /* Browser storage is optional. */ }
    box.addEventListener('toggle', () => {
      try { sessionStorage.setItem(key, box.open ? 'open' : 'closed'); } catch (_) {}
    });
  }

  function reveal(node) {
    for (let parent = node?.parentElement; parent; parent = parent.parentElement) {
      if (parent.matches('details.v855-fold')) parent.open = true;
    }
  }

  function journey(record, body, portal) {
    if (!eligible(record) || body.querySelector('.v855-jump')) return;
    body.classList.add('v855-journey');
    const submissions = portal?.submissions || [];
    const bookingForm = submissions.find(item => item.form_type === 'booking_form');
    const contract = portal?.contract;
    const signed = Boolean(contract && (contract.fully_signed || contract.supplier_signed_at));
    const formReview = (record.tasks || []).some(task => task.workflow_key === 'wbm_review_booking_form' && !task.completed);
    const agreementEmail = (portal?.emails || []).some(email => email.template_key === 'contract_completed' && email.status === 'sent');
    const formsComplete = window.WBMSetup?.native(record) ? (()=>{const p=window.WBMSetup.progress(record,portal);return p.reviewed&&p.confirmed;})() : Boolean(bookingForm && signed && !formReview && agreementEmail);
    const quote = body.querySelector('.v811-journey-quote');
    const forms = body.querySelector('.v811-journey-forms');
    const timings = body.querySelector('.v820-final');
    const call = body.querySelector('.v823-final-call-pack');
    const timingStatus = timings?.querySelector('.v820-state')?.textContent.trim() || 'Open to review';
    const entries = [
      [quote, 'Quote & package', portal?.quote ? 'Accepted · view details' : 'Prepare or review quote', !portal?.quote],
      [forms, 'Booking form & contract', formsComplete ? 'Complete · view saved paperwork' : 'Open to review outstanding steps', !formsComplete],
      [timings, 'Final wedding timings', timingStatus, Boolean(timings?.querySelector('[data-review-final-timings]'))],
      [call, 'Private final-call pack', 'Checklist, notes and PDF', false],
    ];
    const nav = document.createElement('nav');
    nav.className = 'v855-jump';
    nav.setAttribute('aria-label', 'Find booking paperwork');
    for (const [node, title, status, open] of entries) {
      const box = fold(node, title, status, open);
      if (!box) continue;
      rememberPanel(record, box, title, status);
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = title;
      button.onclick = () => { box.open = true; box.scrollIntoView({behavior:'smooth', block:'start'}); box.querySelector('summary').focus(); };
      nav.append(button);
    }
    const root = body.querySelector('.v811-journey');
    if (root) root.prepend(nav);
    const errors = (portal?.emails || []).some(email => email.status === 'failed');
    fold(quote?.querySelector('.workflow-email-proof'), 'Quote email delivery history', errors ? 'Sending issue recorded · review' : 'Sent, opened and link activity', errors);
  }

  function messages(record, body) {
    if (!eligible(record)) return;
    const root = body.querySelector('.v842-email-workspace');
    if (!root) return;
    root.classList.add('v855-messages');
    const conversation = root.querySelector('[data-couple-conversation]');
    const stats = root.querySelector('.v842-email-stats');
    if (conversation && stats) stats.after(conversation);
    const heading = root.querySelector('.v842-email-head h3');
    if (heading) heading.textContent = 'Conversation with the couple';
    const help = root.querySelector('.v842-email-head p');
    if (help) help.textContent = 'Read replies and sent messages below. Delivery records and follow-up controls are grouped underneath.';
    const failed = (state.currentPortal?.emails || []).filter(email => email.status === 'failed').length;
    fold(root.querySelector('.v842-email-log'), 'Booking-system email records', failed ? `${failed} failed · review details` : 'Delivery, detected opens and secure-link visits', Boolean(failed));
    fold(root.querySelector('.workflow-email-proof'), 'Automatic email delivery summary', 'View the recorded booking milestones', false);
  }

  function conversation(record, host) {
    if (!eligible(record)) return;
    const list = host.querySelector('.couple-conversation-list');
    if (!list || !list.querySelector('.couple-message')) return;
    host.classList.add('v855-conversation');
    const tools = document.createElement('div');
    tools.className = 'v855-message-tools';
    const label = document.createElement('label');
    label.textContent = 'Search these messages';
    const input = document.createElement('input');
    input.type = 'search'; input.placeholder = 'Subject or message text';
    label.append(input);
    const filters = document.createElement('div');
    filters.setAttribute('aria-label', 'Message direction');
    const count = document.createElement('span');
    count.className = 'v855-message-count'; count.setAttribute('aria-live', 'polite');
    let direction = 'all';
    const rows = [...list.querySelectorAll('.couple-message')];
    function apply() {
      const term = input.value.trim().toLowerCase();
      let visible = 0;
      rows.forEach(row => {
        row.hidden = !(direction === 'all' || row.classList.contains(direction)) || !row.textContent.toLowerCase().includes(term);
        if (!row.hidden) visible++;
      });
      filters.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.direction === direction)));
      count.textContent = `${visible} of ${rows.length} loaded messages`;
    }
    for (const [key, name] of [['all','All'],['received','Received'],['sent','Sent']]) {
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = name; button.dataset.direction = key;
      button.onclick = () => { direction = key; apply(); };
      filters.append(button);
    }
    input.oninput = apply;
    tools.append(label, filters, count); list.before(tools); apply();
  }
  window.WBMLayoutV855 = Object.freeze({journey, messages, conversation, reveal});
})();
