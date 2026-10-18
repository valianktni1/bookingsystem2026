/* V8.57: named quote offers, selectable wording and bank accounts. */
(() => {
  const pendingEmail = new Map();
  const error = e => toast(e.message, 'error');
  const selected = name => $$(`[name="${name}"]:checked`, $('#modal')).map(x => x.value);
  const options = (items, chosen) => items.map(x => `<option value="${attr(x.id)}" ${x.id===chosen?'selected':''}>${esc(x.name||x.label)}</option>`).join('');
  async function resources() {
    const [catalog, banks, templates] = await Promise.all([api('/api/catalog?brand=wbm'), api('/api/quote-bank-accounts'), api('/api/quote-templates')]);
    return {catalog,banks,templates};
  }
  function fields(res, offer={}) {
    const {catalog,banks}=res;
    const checkList=(items, ids, name)=>items.map(x=>`<label class="v857-check"><input type="checkbox" name="${name}" value="${attr(x.id)}" ${ids==null||ids.includes(x.id)?'checked':''}><span>${esc(x.name)} <small>${money(x.price)}</small></span></label>`).join('');
    const charges=(items, chosen, name)=>items.map(x=>{const old=(chosen||[]).find(v=>v.addon_id===x.id);return `<div class="v857-charge"><label class="v857-check"><input type="checkbox" name="${name}" value="${attr(x.id)}" ${old?'checked':''}><span>${esc(x.name)}</span></label><label>£<input type="number" min="0" max="100000" step="0.01" data-v857-price="${name}-${attr(x.id)}" value="${attr(old?.price??x.price)}" aria-label="${attr(x.name)} amount"></label></div>`}).join('');
    const extras=catalog.addons.filter(x=>!x.is_discount);
    return `<section class="full v857-offer"><h3>Packages the couple can choose</h3><div class="v857-checks">${checkList(catalog.packages,offer.package_ids,'offer-package')}</div><details><summary>Extras the couple can choose</summary><p>Tick to offer an extra. The couple decides whether to add it and pay for it, where their package allows.</p><div class="v857-checks">${checkList(extras,offer.optional_addon_ids,'offer-optional')}</div></details><details ${offer.required_addons?.length?'open':''}><summary>Compulsory extras — automatically included</summary><p>Tick to include and charge this extra on every package offered. The couple cannot remove it. Compulsory takes priority if ticked in both lists; it is charged only once.</p>${charges(extras,offer.required_addons,'offer-required')}</details><details ${offer.discounts?.length?'open':''}><summary>Private discounts</summary>${charges(catalog.addons.filter(x=>x.is_discount),offer.discounts,'offer-discount')}</details><label>Bank account for this quote<select id="offer-bank"><option value="">Keep booking account / existing business details</option>${banks.map(b=>`<option value="${attr(b.id)}" ${b.id===offer.bank_account_id?'selected':''} ${!b.account_number?'disabled':''}>${esc(b.label)}${b.account_number?' · ending '+esc(b.account_number.slice(-4)):' · not set up'}</option>`).join('')}</select></label><p class="muted">Manage your two quote accounts in Business settings. Selected details are saved with this booking.</p></section>`;
  }
  function collect() {
    const charges=name=>selected(name).map(id=>({addon_id:id,price:Number($(`[data-v857-price="${name}-${id}"]`,$('#modal')).value)}));
    const package_ids=selected('offer-package');
    if(!package_ids.length)throw new Error('Choose at least one package');
    const required_addons=charges('offer-required');
    return {package_ids,optional_addon_ids:selected('offer-optional').filter(id=>!required_addons.some(x=>x.addon_id===id)),required_addons,discounts:charges('offer-discount'),bank_account_id:value('#offer-bank')||null};
  }
  async function editTemplate(res, item={}) {
    let subject=item.subject, body=item.body;
    if(!subject) {
      const comm=await api('/api/communications/templates?brand=wbm');
      const base=(comm.templates||[]).find(x=>x.template_key==='quote');
      subject=base?.subject||'Your wedding photography quote';body=base?.body||'Hi {client_first_name},\n\nHere are your wedding photography options.';
    }
    showModal(item.id?'Edit quote template':'New quote template',`<label class="full">Template name<input id="offer-name" maxlength="140" required value="${attr(item.name||'')}"></label>${fields(res,item)}<label class="full">Email subject<input id="offer-subject" maxlength="240" required value="${attr(subject)}"></label><label class="full">Email wording<textarea id="offer-body" rows="10" maxlength="20000" required>${esc(body)}</textarea><small>The tracked quote link is added automatically when sending.</small></label>`,async()=>{
      const payload={...collect(),name:value('#offer-name').trim(),subject:value('#offer-subject').trim(),body:value('#offer-body').trim()};
      await api('/api/quote-templates'+(item.id?'/'+item.id:''),{method:item.id?'PUT':'POST',body:JSON.stringify(payload)});
      closeModal();toast('Quote template saved');await manageTemplates();
    },'A reusable starting point for new quotes. Existing bookings are not changed.');
  }
  async function manageTemplates() {
    try {
      const res=await resources();
      showModal('Quote templates',`<div class="full"><p>Save different package choices, extras, bank account and email wording.</p><button type="button" id="offer-new" class="primary">＋ New quote template</button><div class="v857-template-list">${res.templates.map(t=>`<article><strong>${esc(t.name)}</strong><div><button type="button" data-offer-edit="${attr(t.id)}">Edit</button><button type="button" data-offer-copy="${attr(t.id)}">Duplicate</button><button type="button" data-offer-delete="${attr(t.id)}">Delete</button></div></article>`).join('')||'<p>No saved quote templates yet.</p>'}</div></div>`,()=>closeModal(),'');
      $('#dynamic-form footer .primary').textContent='Done';
      $('#offer-new').onclick=()=>editTemplate(res).catch(error);
      $$('[data-offer-edit]').forEach(b=>b.onclick=()=>editTemplate(res,res.templates.find(x=>x.id===b.dataset.offerEdit)).catch(error));
      $$('[data-offer-copy]').forEach(b=>b.onclick=()=>{const t=res.templates.find(x=>x.id===b.dataset.offerCopy);editTemplate(res,{...t,id:null,name:t.name+' copy'}).catch(error)});
      $$('[data-offer-delete]').forEach(b=>b.onclick=async()=>{if(!confirm('Delete this template? Existing quotes will stay unchanged.'))return;try{await api('/api/quote-templates/'+b.dataset.offerDelete,{method:'DELETE'});await manageTemplates()}catch(e){error(e)}});
    }catch(e){error(e)}
  }
  function insertManager() {
    if($('#v857-template-manager'))return;
    $('#content').insertAdjacentHTML('afterbegin','<section class="panel v857-toolbar" id="v857-template-manager"><div><h2>Quote templates</h2><p>Package choices, extras and email wording for different enquiries.</p></div><button class="primary" id="v857-manage">Manage quote templates</button></section>');
    $('#v857-manage').onclick=manageTemplates;
  }
  const basePackages=renderPackages;
  renderPackages=async function(){await basePackages.apply(this,arguments);if(state.brand!=='ivory')insertManager()};
  const baseComms=renderCommunicationsV2;
  renderCommunicationsV2=async function(){await baseComms.apply(this,arguments);if(state.brand!=='ivory')insertManager()};

  const baseReview=reviewAndSendQuoteEmail;
  reviewAndSendQuoteEmail=async function(r,body){
    await baseReview(r,body);
    if(!$('#quote-email-subject'))return;
    if(window.WBMQuoteReviewV858 && r.brand==='wbm' && r.kind==='wedding' && !r.legacy_source) $('#dynamic-form button[type=submit]').disabled=true;
    try {
      const centre=await api(`/api/bookings/${r.id}/email-centre`);
      const emails=(centre.templates||[]).map(t=>({id:'email:'+t.template_key,name:t.display_name,subject:t.subject,body:t.body}));
      const choices=emails;
      const chosen=pendingEmail.get(r.id);
      $('#quote-email-subject').closest('label').insertAdjacentHTML('beforebegin',`<label class="full">Email wording<select id="v857-email-choice"><option value="">Saved quote wording</option>${options(choices,'')}</select><small>Changes the message only. Packages, extras, discounts and bank details stay as shown in the quote summary.</small></label>`);
      const apply=t=>{if(t){$('#quote-email-subject').value=t.subject;$('#quote-email-body').value=t.body}};
      const saved=chosen||(centre.quote_email?.subject&&centre.quote_email?.body?centre.quote_email:{subject:$('#quote-email-subject').value,body:$('#quote-email-body').value});
      apply(saved);$('#v857-email-choice').value='';
      $('#v857-email-choice').onchange=e=>apply(choices.find(x=>x.id===e.target.value)||saved);
    }catch(e){error(e)}
  };
  prepareQuote=async function(r,body,d){
    try {
      const res=await resources(),sent=latestEmailLog(d,'quote')?.status==='sent';
      let chosen=null;
      showModal(sent?'Edit sent quote':'Prepare quote',`<label class="full">Quote template<select id="v857-offer-choice"><option value="">Current quote / choose manually</option>${options(res.templates)}</select></label><div class="full" id="v857-offer-fields">${fields(res,d.quote_preparation||{})}</div>`,async()=>{
        const payload=collect();
        if(chosen){payload.email_subject=chosen.subject;payload.email_body=chosen.body}
        await api(`/api/bookings/${r.id}/quote/preparation`,{method:'PUT',body:JSON.stringify(payload)});
        if(chosen)pendingEmail.set(r.id,chosen);else pendingEmail.delete(r.id);
        closeModal();toast('Quote saved — nothing has been emailed');await renderQuotePortal(r,body);
        if(!sent)await reviewAndSendQuoteEmail(r,body);
      },sent?'Changes update the existing quote link. Accepted quotes remain locked.':'Choose what this couple can see, then review the email before sending.');
      $('#dynamic-form footer .primary').textContent=sent?'Save quote changes':'Save quote & review email';
      $('#v857-offer-choice').onchange=e=>{chosen=res.templates.find(x=>x.id===e.target.value)||null;$('#v857-offer-fields').innerHTML=fields(res,chosen||d.quote_preparation||{})};
    }catch(e){error(e)}
  };
  async function editBanks(){
    try{
      const banks=await api('/api/quote-bank-accounts');
      showModal('Two bank accounts for new quotes',banks.map(b=>`<fieldset class="full v857-bank" data-bank-id="${attr(b.id)}"><legend>${b.id==='primary'?'Account 1':'Account 2'}</legend><label>Label<input data-bank="label" maxlength="80" required value="${attr(b.label)}"></label><label>Account name<input data-bank="account_name" maxlength="160" value="${attr(b.account_name)}"></label><label>Sort code<input data-bank="sort_code" maxlength="12" inputmode="numeric" value="${attr(b.sort_code)}"></label><label>Account number<input data-bank="account_number" maxlength="8" inputmode="numeric" value="${attr(b.account_number)}"></label></fieldset>`).join(''),async()=>{
        const accounts=$$('[data-bank-id]',$('#modal')).map(el=>Object.fromEntries([['id',el.dataset.bankId],...$$('[data-bank]',el).map(x=>[x.dataset.bank,x.value.trim()])]));
        await api('/api/quote-bank-accounts',{method:'PUT',body:JSON.stringify({accounts})});closeModal();toast('Quote bank accounts saved');
      },'These choices apply when selected for a new quote. Editing them does not change saved quote bank details or existing invoices. Leave an unused account completely blank.');
    }catch(e){error(e)}
  }
  const baseSettings=renderSettings;
  renderSettings=function(){const result=baseSettings.apply(this,arguments);if(state.brand!=='ivory'){
    $('#content').insertAdjacentHTML('afterbegin','<section class="panel v857-toolbar"><div><h2>Bank accounts for new quotes</h2><p>Choose your current or new business account when preparing a quote.</p></div><button class="primary" id="v857-banks">Manage two bank accounts</button></section>');$('#v857-banks').onclick=editBanks;
  }return result};
})();

