/* V8.61: read-only paperwork views and direct dashboard review destinations. */
(() => {
  'use strict';
  const native = r => r?.brand === 'wbm' && r.kind === 'wedding' && !r.legacy_source;
  const lines = value => esc(value || '').replace(/\r\n?/g,'\n').replace(/[•●▪]\s*/g,'\n').replace(/\n/g,'<br>');
  function modal(title, record, content) {
    const root = $('#modal-content');
    $('#modal').classList.remove('pdf-preview-modal','hidden');
    $('#modal-overlay').classList.remove('hidden');
    root.innerHTML = `<div class="modal-head"><div><small>BOOKING PAPERWORK</small><h2>${esc(title)}</h2><p>${esc(record.title)}</p></div><button type="button" id="close-modal" aria-label="Close">×</button></div><div class="v861-paper">${content}</div><footer class="v861-footer"><button type="button" class="secondary" data-paper-close>Close</button></footer>`;
    $('#close-modal').onclick = $('[data-paper-close]',root).onclick = closeModal;
    $('#modal').scrollTop = 0;
    $('#close-modal').focus({preventScroll:true});
    return $('.v861-paper',root);
  }
  function quoteContent(r, d) {
    const q = d.quote;
    if (!q) return `<p>${d.quote_preparation?.prepared ? 'Saved quote — awaiting their package choice.' : 'No accepted quote is recorded yet.'}</p><p>Preview the packages and extras currently offered to this couple.</p><a class="primary v861-link" href="/quote-preview/${encodeURIComponent(r.id)}" target="_blank" rel="noopener">Preview offered quote ↗</a>`;
    return `<div class="v861-status"><strong>${esc(q.status || 'Accepted')} quote</strong><span>${q.accepted_at ? esc(fmtDateTime(q.accepted_at)) : ''}</span></div><div class="v861-items">${(q.line_items || []).map(item => `<article><header><strong>${esc(item.name || 'Quote item')}</strong><b>${money(item.total)}</b></header>${item.description ? `<p>${lines(item.description)}</p>` : ''}</article>`).join('') || '<p>No saved line items are available for this quote.</p>'}</div><div class="v861-total"><strong>Quote total</strong><b>${money(q.total)}</b></div><p class="muted">Booking fee: ${money(q.deposit_amount)}. These are the saved quote details, not today’s package prices.</p>`;
  }
  async function viewQuote(r) {
    const host=modal('Quote & package',r,'<p>Loading saved quote…</p>');
    try { const d=await api(`/api/bookings/${r.id}/portal`); if(host.isConnected)host.innerHTML=quoteContent(r,d); }
    catch(e){if(host.isConnected)host.textContent=e.message;}
  }
  function answers(data, snapshot) {
    const excluded = new Set(['answer_snapshot','_answer_snapshot','form_template_updated_at','_form_template_updated_at','custom_answers','venue_lat','venue_lng','venue_place_id']);
    const entries = Array.isArray(snapshot) && snapshot.length ? snapshot.map(x=>[x.label || questionnaireLabel(x.key),x.answer]) :
      Object.entries(data || {}).filter(([k])=>!excluded.has(k)&&!k.startsWith('_')).map(([k,v])=>[questionnaireLabel(k),v]);
    if (!snapshot?.length) for (const [k,v] of Object.entries(data?.custom_answers || {})) entries.push([questionnaireLabel(k),v]);
    return `<dl class="v861-answers">${entries.map(([label,value])=>`<div><dt>${esc(label)}</dt><dd>${lines(value === true ? 'Yes' : value === false ? 'No' : value == null || value === '' ? 'Not supplied' : typeof value === 'object' ? JSON.stringify(value,null,2) : value)}</dd></div>`).join('')}</dl>`;
  }
  async function viewEnquiry(r) {
    const host=modal('Original enquiry',r,'<p>Loading original enquiry…</p>');
    try {
      const original=await api(`/api/bookings/${r.id}/original-enquiry`);
      if(!host.isConnected)return;
      if(original.source==='website_submission') host.innerHTML=`<p class="muted">Original website submission${original.received_at ? ' · '+esc(fmtDateTime(original.received_at)) : ''}</p>${answers(original.answers,original.answers?.answer_snapshot)}`;
      else if(original.source==='saved_notification') host.innerHTML=`<p class="muted">Saved original enquiry-notification email · ${esc(fmtDateTime(original.received_at))}. The structured website submission is no longer available.</p><h3>${esc(original.subject)}</h3><div class="v861-original-email">${lines(original.body)}</div>`;
      else host.innerHTML='<p>No original website enquiry or saved enquiry-notification email is available with this booking. It may have been entered manually or imported.</p><p>Current booking details are not presented as the original enquiry.</p>';
    }catch(e){if(host.isConnected)host.textContent=e.message;}
  }
  async function direct(r, action) {
    if (!['review_quote','review_booking_form','review_final_timings','review_forms','review_agreement','countersign','review_confirmation'].includes(action)) return false;
    if (action==='review_quote' && native(r)) {await viewQuote(r);return true;}
    if (native(r) && ['countersign','review_confirmation','review_forms'].includes(action)) {
      await selectRecordTab(r,'Journey');
      if(state.current?.id!==r.id)return true;
      const body=$('#drawer-body');
      const selector=action==='countersign'?'[data-countersign-contract]':action==='review_confirmation'?'[data-send-contract-completion]':'.v811-journey-forms';
      const target=body?.querySelector(selector)||body?.querySelector('.agreement-summary')||body?.querySelector('.v811-journey-forms');
      if(target){window.WBMLayoutV855?.reveal(target);target.scrollIntoView({behavior:'smooth',block:'center'});if(target.matches('button'))target.focus({preventScroll:true});}
      return true; // Navigation never signs or sends; explicit controls retain confirmation.
    }
    if (['review_forms','review_agreement','countersign'].includes(action)) {
      const d=await api(`/api/bookings/${r.id}/portal`);
      if (state.current?.id !== r.id) return true;
      if (!d.contract || d.contract.is_legacy_import) return false;
      showPdfPreview('Wedding agreement',`/api/bookings/${r.id}/contract.pdf?inline=true`,`/api/bookings/${r.id}/contract.pdf`);
      return true;
    }
    if(action==='review_final_timings') {
      const d=await api(`/api/bookings/${r.id}/portal`);
      if(state.current?.id !== r.id)return true;
      if(!(d.submissions||[]).some(x=>x.form_type==='final_timings'))return false;
      state.currentPortal=d; await window.openFinalTimingsRecord(r);return true;
    }
    if(action==='review_booking_form') {
      const host=modal('Wedding Booking Form',r,'<p>Loading submitted answers…</p>');
      try {
        const d=await api(`/api/bookings/${r.id}/portal`);
        if(!host.isConnected)return true;
        const sub=(d.submissions||[]).find(x=>x.form_type==='booking_form');
        host.innerHTML=sub ? `<p class="muted">Submitted ${esc(fmtDateTime(sub.updated_at || sub.submitted_at))}</p>${answers(sub.data,r.form_data?._answer_snapshot || sub.data?._answer_snapshot)}` : '<p>No submitted booking form is available.</p>';
        if(sub && native(r) && (r.tasks||[]).some(t=>t.workflow_key==='wbm_review_booking_form'&&!t.completed)) {
          host.insertAdjacentHTML('beforeend','<button type="button" class="primary" data-confirm-form-review>I’ve reviewed this booking form</button>');
          $('[data-confirm-form-review]',host).onclick=async event=>{
            const button=event.currentTarget;button.disabled=true;
            try {await api(`/api/bookings/${r.id}/booking-form/review`,{method:'POST'});button.textContent='Reviewed';toast('Booking form marked as reviewed');await refresh();}
            catch(e){button.disabled=false;toast(e.message,'error');}
          };
        }
      } catch(e){if(host.isConnected)host.textContent=e.message;}
      return true;
    }
    return false;
  }
  function tidyQuote(r,body,d) {
    if(!native(r))return false;
    // Messages already has these exact histories; do not repeat them here.
    body.querySelectorAll('.workflow-email-proof,.email-history-list,[data-couple-conversation],.portal-progress').forEach(node=>node.remove());
    body.querySelectorAll('.section-title').forEach(node=>{if(node.textContent.trim()==='Email history')node.remove();});
    const quote=body.querySelector('.quote-send-card');
    if(quote) {
      const detail=document.createElement('section');detail.className='v861-quote-details';
      detail.innerHTML=quoteContent(r,d);quote.after(detail);
    }
    const controls=document.createElement('details');controls.className='v861-access';
    controls.innerHTML='<summary>Client access & sending controls</summary>';
    const nodes=[...body.children].filter(n=>n.matches('.portal-link,.portal-email,.section-actions'));
    if(nodes.length){nodes.forEach(n=>controls.append(n));body.append(controls);}
    const messages=document.createElement('button');messages.type='button';messages.className='secondary';messages.textContent='View emails & delivery history';messages.onclick=()=>selectRecordTab(r,'Emails');body.append(messages);
    return true;
  }
  function shortcuts(r) {
    if(!native(r))return;
    const nav=$('#drawer .record-contact-actions');
    if(!nav || nav.querySelector('[data-v861-quote]'))return;
    nav.insertAdjacentHTML('afterbegin','<button type="button" data-v861-quote>View quote</button><button type="button" data-v861-enquiry>Original enquiry</button>');
    $('[data-v861-quote]',nav).onclick=()=>viewQuote(r);
    $('[data-v861-enquiry]',nav).onclick=()=>viewEnquiry(r);
  }
  const select=selectRecordTab;
  selectRecordTab=async function(r,...args){const result=await select(r,...args);shortcuts(r);return result;};
  const renderPortal=renderQuotePortal;
  renderQuotePortal=async function(r,body){
    const result=await renderPortal(r,body);
    if(native(r)) {
      const reset=body.querySelector('.v82-reset-panel');
      if(reset){const box=document.createElement('details');box.className='v861-access';box.innerHTML='<summary>Correct submitted paperwork</summary>';reset.before(box);box.append(reset);}
    }
    return result;
  };
  window.WBMReview={direct,tidyQuote,quoteContent,viewQuote,viewEnquiry};
})();
