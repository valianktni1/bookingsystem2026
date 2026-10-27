/* Booking workspace presentation. Existing send/payment handlers and import protections remain authoritative. */
(() => {
  'use strict';
  const native=r=>r?.brand==='wbm'&&r.kind==='wedding'&&!r.legacy_source;
  const opening=new Set();
  const appearance=()=>'<label class="v866-appearance">Appearance<select data-wbm-appearance aria-label="Appearance"><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label>';
  document.querySelector('.topbar')?.insertAdjacentHTML('beforeend',appearance());
  window.WBMAppearance.apply();
  function decorate(r) {
    const drawer=document.querySelector('#drawer');if(!drawer)return;
    drawer.classList.toggle('v866-workspace',native(r));
    const bar=drawer.querySelector('.record-command-bar');
    const menu=drawer.querySelector('#record-actions-menu');
    if(bar&&!drawer.querySelector('[data-wbm-appearance]')){(native(r)&&menu?menu:bar).insertAdjacentHTML('beforeend',appearance());window.WBMAppearance.apply();}
    if(!native(r))return;
    // Keep bound shortcuts accessible, without repeating them across the header.
    if(menu)drawer.querySelectorAll('.record-contact-actions > *').forEach(node=>menu.append(node));
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
  function fold(title,rows){return rows.length?`<details class="v872-fold"><summary>${esc(title)} (${rows.length})</summary>${rows.join('')}</details>`:'';}
  const previousOverview=renderOverview;
  renderOverview=function(r,body){
    previousOverview(r,body);
    if(!native(r))return;
    const portal=state.currentPortal||{},submissions=portal.submissions||[];
    const setup=window.WBMSetup.progress(r,portal),facts=recordJourneyFacts(r,portal);
    const form=submissions.find(x=>x.form_type==='booking_form'),timings=submissions.find(x=>x.form_type==='final_timings');
    const quote=portal.quote,prepared=portal.quote_preparation?.prepared,quoteSent=facts.quoteSent;
    const board=body.querySelector('.v830-job-board');if(!board)return;
    const active=[],completed=[],later=[];
    active.push(row('Original enquiry','The original message and submitted answers','enquiry'));
    (quote?completed:active).push(row('Quote & package',quote?'Accepted · saved package details':quoteSent?'Sent · waiting for their choice':prepared?'Prepared · not sent':'Not prepared','quote',quote||quoteSent?'View':prepared?'Review & send':'Prepare'));
    const bookingStarted=Boolean(quote||facts.hasPayment||form||portal.contract);
    (setup.reviewed?completed:bookingStarted?active:later).push(row('Wedding booking form',form?(setup.reviewed?'Reviewed · saved answers':'Submitted · needs your review'):bookingStarted?'Waiting for the couple':'After quote acceptance',form?'form':'forms'));
    (setup.confirmed?completed:bookingStarted?active:later).push(row('Agreement',setup.confirmed?'Signed & confirmation sent':setup.signed?'Signed · check confirmation':portal.contract?'Review signature status':bookingStarted?'Waiting for the couple':'After quote acceptance','agreement'));
    const eventDay=Date.parse((r.event_date||'')+'T12:00:00Z'),daysAway=(eventDay-Date.now())/86400000;
    const nearWedding=bookingStarted&&Number.isFinite(daysAway)&&daysAway<=30;
    const timingReview=(r.tasks||[]).some(t=>t.workflow_key==='wbm_review_final_timings'&&!t.completed);
    (timings?(timingReview?active:completed):nearWedding?active:later).push(row('Final timings',timings?(timingReview?'Submitted · needs your review':'Submitted · saved answers'):nearWedding?'No submission yet':'Later in wedding planning','timings'));
    if((r.documents||[]).length)active.push(row('Files & attachments',`${r.documents.length} saved`,'files'));
    const newBoard=document.createElement('div');newBoard.className='v866-board v872-board';
    newBoard.innerHTML=`<div class="v866-left"><section class="v866-panel"><header><h2>Booking documents</h2><span>${setup.count}/4 setup steps complete</span></header>${active.join('')}${fold('Completed paperwork',completed)}${fold('Later in the booking',later)}</section><section class="v866-panel"><header><h2>Recent messages</h2><button type="button" class="secondary" data-v866-action="messages">Open messages</button></header><div data-v866-mail><p>Loading recent messages…</p></div></section></div><div class="v866-right"><details class="v866-panel v872-details"><summary>Couple &amp; wedding details</summary><div data-v872-details></div></details></div>`;
    const left=newBoard.querySelector('.v866-left'),right=newBoard.querySelector('.v866-right');
    // Move existing cards to preserve all edit, finance and private-note handlers.
    const cards=body.querySelector('.v830-top-cards');if(cards)newBoard.querySelector('[data-v872-details]').append(cards);
    const payment=body.querySelector('.v830-summary-stack');if(payment){
      if(!quote&&!facts.hasPayment&&!(r.invoices||[]).length){const box=document.createElement('details');box.className='v866-panel v872-details v879-later-payments';box.innerHTML='<summary>Payments · after quote acceptance</summary><p>Accepting a quote creates its invoice automatically. Record the first payment when it arrives.</p>';box.append(payment);right.prepend(box)}else right.prepend(payment);
    }
    const notes=body.querySelector('.v863-private');if(notes)left.append(notes);
    const bank=body.querySelector('.v858-bank');if(bank){const box=document.createElement('details');box.className='v866-panel v872-details';box.innerHTML='<summary>Payment account &amp; quote preview</summary>';box.append(bank);right.append(box);}
    board.before(newBoard);board.remove();body.querySelector('.v863-progress')?.remove();
    const actions={
      enquiry:()=>window.WBMReview.viewEnquiry(r),
      quote:()=>quote||quoteSent?window.WBMReview.viewQuote(r):go(r,'Journey','#send-quote').then(()=>{if(state.current?.id===r.id)document.querySelector('#send-quote')?.click();}),
      form:()=>window.WBMReview.direct(r,'review_booking_form'),
      forms:()=>go(r,'Journey','.v811-journey-forms'),
      agreement:()=>portal.contract?window.WBMReview.direct(r,setup.signed&&!setup.confirmed?'review_confirmation':!setup.signed?'countersign':'review_agreement'):go(r,'Journey','.v811-journey-forms'),
      timings:()=>window.openFinalTimingsRecord(r),messages:()=>selectRecordTab(r,'Emails',true),files:()=>selectRecordTab(r,'Files',true)
    };
    newBoard.querySelectorAll('[data-v866-action]').forEach(b=>b.onclick=()=>Promise.resolve(actions[b.dataset.v866Action]()).catch(e=>toast(e.message,'error')));
    const host=newBoard.querySelector('[data-v866-mail]');
    api(`/api/bookings/${r.id}/conversation?limit=10`).then(d=>{
      if(!host.isConnected)return;
      const rows=[...(d.messages||[])].sort((a,b)=>String(b.date||'').localeCompare(String(a.date||''))||String(b.id||'').localeCompare(String(a.id||''))).slice(0,3);
      host.innerHTML=rows.length?rows.map(m=>`<button type="button" class="v866-message"><strong>${esc(m.subject||'(No subject)')}</strong><small>${m.direction==='received'?'Received':'Sent'} · ${esc(fmtDateTime(m.date))}</small><span>Open conversation →</span></button>`).join(''):'<p>No linked correspondence yet.</p>';
      if(d.incoming_error)host.insertAdjacentHTML('beforeend','<p>Some mailbox messages could not be loaded. Open Messages for details.</p>');
      host.querySelectorAll('button').forEach((b,index)=>b.onclick=()=>window.WBMFlowV878?window.WBMFlowV878.openMessage(r,rows[index].id):selectRecordTab(r,'Emails',true));
    }).catch(()=>{if(host.isConnected)host.innerHTML='<p>Recent messages could not be loaded. Open Messages to retry.</p>';});
  };
  const select=selectRecordTab;
  let selection=0;
  selectRecordTab=async function(r,...args){
    const revision=++selection;
    if(native(r)&&normaliseRecordTab(args[0])==='Overview'&&!(opening.has(r.id)&&state.current?.id===r.id&&state.currentPortal)){
      try {const portal=await api(`/api/bookings/${r.id}/portal`);if(revision!==selection||state.current?.id!==r.id)return;state.currentPortal=portal;}
      catch(e){if(revision!==selection)return;toast('Could not refresh booking status. Showing the last loaded details.','error');}
    }
    const result=await select(r,...args);decorate(r);return result;
  };
  window.addEventListener('resize',()=>decorate(state.current));
  const open=openDrawer;
  openDrawer=async function(id,...args){opening.add(id);try{const result=await open(id,...args);decorate(state.current);return result;}finally{opening.delete(id);}};
  let pending=false;
  new MutationObserver(()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;const drawer=document.querySelector('#drawer');if(drawer&&!drawer.classList.contains('hidden')&&!drawer.querySelector('[data-wbm-appearance]'))decorate(state.current);});}).observe(document.querySelector('#drawer'),{childList:true});
})();

