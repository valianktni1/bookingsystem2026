/* V8.63: one booking-setup checklist, safe direct actions and a concise Overview. */
(() => {
  'use strict';
  const native = r => r?.brand === 'wbm' && r.kind === 'wedding' && !r.legacy_source;
  // SQLite timestamps can be naive; server timestamps without an offset are UTC.
  const timestamp = value => value ? Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value+'Z') : NaN;
  function progress(r, p = {}) {
    p = p || {};
    const f = recordJourneyFacts(r,p), c = p.contract;
    const signed = Boolean(c?.accepted_at && c?.supplier_signed_at);
    const confirmed = signed && (p.emails || []).some(e => e.template_key === 'contract_completed' && e.status === 'sent' && timestamp(e.sent_at) >= Math.max(timestamp(c.accepted_at),timestamp(c.supplier_signed_at)));
    const reviewed = Boolean(f.bookingForm && !f.bookingFormReview);
    const steps = [
      {label:'Quote',done:Boolean(f.quote),detail:f.quote?'Accepted':f.quoteSent?'Waiting for their choice':'Not sent',tab:'Journey'},
      {label:'First payment',done:Boolean(f.hasPayment),detail:f.hasPayment?'Date secured':'Not recorded',tab:'Payments'},
      {label:'Booking form',done:reviewed,detail:reviewed?'Reviewed':f.bookingForm?'Needs your review':'Waiting for the couple',tab:'Journey'},
      {label:'Agreement',done:Boolean(confirmed),detail:confirmed?'Signed & confirmation sent':signed?'Confirmation needs attention':c?'Your signature needed':'Waiting for the couple',tab:'Journey'},
    ];
    return {steps,confirmed,signed,reviewed,count:steps.filter(s=>s.done).length};
  }
  function checklist(r,p) {
    const data=progress(r,p);
    return `<section class="v863-progress"><header><strong>Booking setup</strong><span>${data.count}/4 complete</span></header><div>${data.steps.map(s=>`<article class="${s.done?'done':'waiting'}"><b aria-hidden="true">${s.done?'✓':'○'}</b><span><strong>${esc(s.label)}</strong><small>${esc(s.detail)}</small></span></article>`).join('')}</div><p>Final timings, the wedding and delivery are tracked separately.</p></section>`;
  }
  window.WBMSetup = {native,progress,checklist};
  const oldNext=recordNextAction;
  recordNextAction=function(r,p={}) {
    const next=oldNext(r,p);
    if(!native(r)||['completed','cancelled'].includes(r.status))return next;
    const data=progress(r,p);
    if(data.signed&&!data.confirmed)return {title:'Check the agreement confirmation',detail:'Both signatures are recorded. The confirmation email still needs attention.',tab:'Journey',action:'review_confirmation',label:'Review confirmation'};
    return next;
  };
  const oldStrip=recordJourneyStrip;
  recordJourneyStrip=function(r,p){return native(r)?checklist(r,p):oldStrip(r,p);};
  const oldOverview=renderOverview;
  renderOverview=function(r,body){
    oldOverview(r,body);
    if(!native(r))return;
    body.classList.add('v863-overview');
    body.insertAdjacentHTML('afterbegin',checklist(r,state.currentPortal||{}));
    // The header already supplies the next action. Keep only useful booking facts here.
    body.querySelector('.v830-job-left')?.remove();
    body.querySelector('.v830-job-board')?.classList.add('v863-summary-board');
    const cards=body.querySelectorAll('.v830-info-card header strong');
    if(cards[0])cards[0].textContent='Wedding details';
    if(cards[1])cards[1].textContent='The couple';
    const notes=body.querySelector('.v830-summary-stack');
    if(notes){
      notes.insertAdjacentHTML('afterend',`<details class="v863-private"><summary>Private notes & tasks · ${(r.tasks||[]).filter(t=>!t.completed).length} open</summary><div class="v863-private-body"><p>${esc(r.notes||'No main notes added.')}</p><button type="button" class="secondary" data-v863-notes>Open notes & activity</button></div></details>`);
      // Retain payment summary, remove the repeated notes/task navigation card.
      const children=[...notes.children];if(children.length>1)children[1].remove();
      body.querySelector('[data-v863-notes]').onclick=()=>selectRecordTab(r,'Activity',true);
    }
  };
})();
