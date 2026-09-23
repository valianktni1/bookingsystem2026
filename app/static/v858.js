/* Owner review controls; no portal tokens, emails or booking mutations. */
(() => {
  window.WBMQuoteReviewV858 = true;
  const eligible=r=>r?.brand==='wbm'&&r.kind==='wedding'&&!r.legacy_source;
  const bankText=b=>`${b?.label||'Existing business account'}${b?.account_number?' · ending '+String(b.account_number).slice(-4):' · account number not set'}`;
  const previewLink=r=>`<a class="secondary" href="/quote-preview/${encodeURIComponent(r.id)}" target="_blank" rel="noopener">Preview as the couple ↗</a>`;
  function summary(d){
    const offer=d.quote_preparation||{},required=offer.required_addons||[],discounts=offer.discounts||[];
    const adjustment=required.reduce((n,x)=>n+Number(x.price),0)-discounts.reduce((n,x)=>n+Number(x.price),0);
    const lines=(rows,minus=false)=>rows.map(x=>`<li><span>${esc(x.name)}</span><b>${minus?'−':''}${money(x.price)}</b></li>`).join('');
    const requiredIds=required.map(x=>x.addon_id);
    const extras=d.catalog.addons.filter(x=>!requiredIds.includes(x.id)&&(!x.eligible_package_codes.length||d.catalog.packages.some(p=>x.eligible_package_codes.includes(p.code))));
    return `<section class="full v858-summary"><h3>Check this quote before sending</h3><p>Each price below includes compulsory extras and discounts. Optional extras cost more if chosen.</p><ul>${d.catalog.packages.map(p=>`<li><span>${esc(p.name)}</span><b>${money(Number(p.price)+adjustment)}</b></li>`).join('')||'<li>No active packages available — edit the quote before sending.</li>'}</ul>${required.length?`<details><summary>Automatically included (${required.length})</summary><ul>${lines(required)}</ul></details>`:''}${discounts.length?`<details><summary>Discounts (${discounts.length})</summary><ul>${lines(discounts,true)}</ul></details>`:''}<details><summary>Extras the couple can choose (${extras.length})</summary><ul>${lines(extras)||'<li>No optional extras offered.</li>'}</ul><p>Availability follows each package’s eligibility rules.</p></details><p><strong>Payment account:</strong> ${esc(bankText(d.preview_bank))}</p><small>${esc(d.preview_bank?.account_name||'No account name set')}${d.preview_bank?.sort_code?' · '+esc(d.preview_bank.sort_code):''}</small></section>`;
  }
  const baseReview=reviewAndSendQuoteEmail;
  reviewAndSendQuoteEmail=async function(r,body){
    await baseReview(r,body);
    if(!eligible(r)||!$('#quote-email-subject'))return;
    const form=$('#dynamic-form'),send=form.querySelector('button[type="submit"]');
    send.disabled=true;
    try{
      const d=await api(`/api/bookings/${r.id}/quote-preview-data`);
      if(form!==$('#dynamic-form'))return;
      form.querySelector('.form-grid').insertAdjacentHTML('afterbegin',summary(d)+`<div class="full v858-preview">${previewLink(r)}<small>Opens the saved quote in a separate tab. Nothing is sent or accepted.</small></div>`);
      send.disabled=!d.catalog.packages.length||d.catalog.packages.some(p=>Number(p.price)+(d.quote_preparation.required_addons||[]).reduce((n,x)=>n+Number(x.price),0)-(d.quote_preparation.discounts||[]).reduce((n,x)=>n+Number(x.price),0)<0);
      if(send.disabled)$('#form-error').textContent='Review the package choices and discounts before sending.';
    }catch(e){if(form===$('#dynamic-form'))$('#form-error').textContent='Could not load the quote summary. Close and reopen to try again. '+e.message}
  };
  const baseOverview=renderOverview;
  renderOverview=function(r,body){
    const result=baseOverview.apply(this,arguments);
    if(!eligible(r))return result;
    const wf=r.workflow_state||{},saved=wf.quote_preparation?.bank_details;
    const profile=(state.businesses||[]).find(x=>x.brand==='wbm');
    const bank=saved||profile?.bank_details||{};
    const invoices=(r.invoices||[]).filter(x=>!['void','cancelled'].includes(x.status));
    const rows=invoices.map(x=>`<li><span>${esc(x.number)}</span><span>${esc(bankText(wf.invoice_bank_details?.[x.id]||profile?.bank_details||{}))}</span></li>`).join('');
    body.insertAdjacentHTML('beforeend',`<section class="v858-bank"><div><small>PAYMENT ACCOUNT FOR THIS BOOKING</small><strong>${esc(bankText(bank))}</strong><span>${saved?'Saved with this quote':'Using existing business details'}</span></div>${previewLink(r)}${rows?`<details><summary>Account on each invoice</summary><ul>${rows}</ul></details>`:''}</section>`);
    return result;
  };
})();
