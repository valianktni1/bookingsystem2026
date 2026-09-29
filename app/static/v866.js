/* Presentation only. Existing renderers, protection checks and send handlers remain authoritative. */
(() => {
  'use strict';
  const native=r=>r?.brand==='wbm'&&r.kind==='wedding'&&!r.legacy_source;
  const appearance=()=>'<label class="v866-appearance">Appearance<select data-wbm-appearance aria-label="Appearance"><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label>';
  document.querySelector('.topbar')?.insertAdjacentHTML('beforeend',appearance());
  window.WBMAppearance.apply();
  function decorate(r) {
    const drawer=document.querySelector('#drawer');if(!drawer)return;
    drawer.classList.toggle('v866-workspace',native(r));
    const bar=drawer.querySelector('.record-command-bar');
    if(bar&&!bar.querySelector('[data-wbm-appearance]')){bar.insertAdjacentHTML('beforeend',appearance());window.WBMAppearance.apply();}
    if(!native(r))return;
    const labels={Journey:'Quote & forms',Emails:'Messages',Activity:'Notes & activity'};
    drawer.querySelectorAll('[data-tab]').forEach(b=>{const title=b.querySelector('strong');if(title&&labels[b.dataset.tab])title.textContent=labels[b.dataset.tab];});
  }
  async function go(r,tab,selector) {
    await selectRecordTab(r,tab,true);
    if(state.current?.id!==r.id||!selector)return;
    const el=document.querySelector('#drawer '+selector);
    if(!el)return;
    for(let p=el.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
    el.scrollIntoView({block:'center',behavior:'smooth'});
    el.focus({preventScroll:true});
  }
  function row(title,detail,action,label='View') {
    return `<div class="v866-doc"><div><strong>${esc(title)}</strong><small>${esc(detail)}</small></div><button type="button" class="secondary" data-v866-action="${action}">${label}</button></div>`;
  }
  const previousOverview=renderOverview;
  renderOverview=function(r,body){
    previousOverview(r,body);
    if(!native(r))return;
    const portal=state.currentPortal||{},submissions=portal.submissions||[];
    const setup=window.WBMSetup.progress(r,portal);
    const form=submissions.find(x=>x.form_type==='booking_form'),timings=submissions.find(x=>x.form_type==='final_timings');
    const quote=portal.quote,prepared=portal.quote_preparation?.prepared;
    const quoteSent=(portal.emails||[]).some(x=>x.template_key==='quote'&&x.status==='sent');
    const board=body.querySelector('.v830-job-board');
    if(!board)return;
    const oldChecklist=body.querySelector('.v863-progress');
    const newBoard=document.createElement('div');newBoard.className='v866-board';
    newBoard.innerHTML=`<div class="v866-left"><section class="v866-panel"><header><h2>Wedding workflow</h2><span>${setup.count}/4 booking steps complete</span></header><div class="v866-workflow">${setup.steps.map((s,i)=>`<button type="button" data-v866-step="${i}"><b>${s.done?'✓':i+1}</b><span><strong>${esc(s.label)}</strong><small>${esc(s.detail)}</small></span><em>›</em></button>`).join('')}<button type="button" data-v866-action="timings"><b>${timings?'✓':'5'}</b><span><strong>Final timings</strong><small>${timings?'Submitted · view answers':'No submission yet'}</small></span><em>›</em></button></div></section><section class="v866-panel"><header><h2>Correspondence</h2><button type="button" class="secondary" data-v866-action="messages">Open messages</button></header><div data-v866-mail><p>Loading recent correspondence…</p></div></section></div><div class="v866-right"><section class="v866-panel"><header><h2>Documents &amp; forms</h2></header>${row('Original enquiry','The saved original message and answers','enquiry')}${row('Quote & package',quote?'Accepted · saved package details':quoteSent?'Sent · waiting for their choice':prepared?'Prepared · not sent':'Not prepared','quote',quote||quoteSent?'View':prepared?'Review':'Prepare')}${row('Wedding booking form',form?'Submitted · saved answers':'Not submitted',form?'form':'forms')}${row('Agreement',setup.confirmed?'Signed & confirmation sent':setup.signed?'Signed · check confirmation':portal.contract?'Review signature status':'Not signed','agreement')}${row('Final timings',timings?'Submitted · saved answers':'No submission yet','timings')}${row('Files & attachments',`${(r.documents||[]).length} saved`,'files')}</section></div>`;
    const left=newBoard.querySelector('.v866-left'),right=newBoard.querySelector('.v866-right');
    // Move existing cards rather than rebuilding them: retain edit links, finance and notes handlers.
    const cards=body.querySelector('.v830-top-cards');if(cards)right.prepend(cards);
    const payment=body.querySelector('.v830-summary-stack');if(payment)right.append(payment);
    const notes=body.querySelector('.v863-private');if(notes)left.append(notes);
    const bank=body.querySelector('.v858-bank');if(bank)right.append(bank);
    board.before(newBoard);board.remove();oldChecklist?.remove();
    const actions={
      enquiry:()=>window.WBMReview.viewEnquiry(r),
      quote:()=>quote||quoteSent?window.WBMReview.viewQuote(r):go(r,'Journey','#send-quote').then(()=>{if(state.current?.id===r.id)document.querySelector('#send-quote')?.click();}),
      form:()=>window.WBMReview.direct(r,'review_booking_form'),
      forms:()=>go(r,'Journey','.v811-journey-forms'),
      agreement:()=>portal.contract?window.WBMReview.direct(r,'review_agreement'):go(r,'Journey','.v811-journey-forms'),
      timings:()=>window.openFinalTimingsRecord(r),messages:()=>selectRecordTab(r,'Emails',true),files:()=>selectRecordTab(r,'Files',true)
    };
    newBoard.querySelectorAll('[data-v866-action]').forEach(b=>b.onclick=()=>Promise.resolve(actions[b.dataset.v866Action]()).catch(e=>toast(e.message,'error')));
    newBoard.querySelectorAll('[data-v866-step]').forEach(b=>b.onclick=()=>go(r,setup.steps[Number(b.dataset.v866Step)].tab,Number(b.dataset.v866Step)>1?'.v811-journey-forms':null));
    const host=newBoard.querySelector('[data-v866-mail]');
    api(`/api/bookings/${r.id}/conversation?limit=3`).then(d=>{
      if(!host.isConnected)return;
      const rows=(d.messages||[]).slice(0,3);
      host.innerHTML=rows.length?rows.map(m=>`<button type="button" class="v866-message"><strong>${esc(m.subject||'(No subject)')}</strong><small>${m.direction==='received'?'Received':'Sent'} · ${esc(fmtDateTime(m.date))}</small><span>Open conversation →</span></button>`).join(''):'<p>No linked correspondence yet.</p>';
      host.querySelectorAll('button').forEach(b=>b.onclick=()=>selectRecordTab(r,'Emails',true));
    }).catch(()=>{if(host.isConnected)host.innerHTML='<p>Open Messages to view correspondence and delivery records.</p>';});
  };
  const select=selectRecordTab;
  let selection=0;
  selectRecordTab=async function(r,...args){
    const revision=++selection;
    if(native(r)&&normaliseRecordTab(args[0])==='Overview'){
      try {const portal=await api(`/api/bookings/${r.id}/portal`);if(revision!==selection||state.current?.id!==r.id)return;state.currentPortal=portal;}
      catch(e){if(revision!==selection)return;toast('Could not refresh booking status. Showing the last loaded details.','error');}
    }
    const result=await select(r,...args);decorate(r);return result;
  };
  const open=openDrawer;
  openDrawer=async function(...args){const result=await open(...args);decorate(state.current);return result;};
  // Routes restored on reload use the existing controller; decorate their shell as well.
  let pending=false;
  new MutationObserver(()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;const drawer=document.querySelector('#drawer');if(drawer&&!drawer.classList.contains('hidden')&&!drawer.querySelector('[data-wbm-appearance]'))decorate(state.current);});}).observe(document.querySelector('#drawer'),{childList:true});
})();
