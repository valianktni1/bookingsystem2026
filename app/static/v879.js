/* Stage-aware presentation. Existing invoice/payment/communication handlers stay authoritative. */
(() => {
  'use strict';
  const native = r => window.WBMSetup?.native(r);
  const oldNext = recordNextAction;
  recordNextAction = function(r,p) {
    const next = oldNext(r,p);
    if (!native(r)) return next;
    const labels = {send_quote:'Prepare quote',view_quote:'View quote',review_forms:'View paperwork',record_payment:'Open payments'};
    return labels[next.action] ? {...next,label:labels[next.action]} : next;
  };
  const oldFinance = renderFinance;
  renderFinance = function(r,body) {
    const result = oldFinance.apply(this,arguments);
    if (!native(r)) return result;
    const header = body.querySelector('.section-actions');
    const create = body.querySelector('#new-invoice');
    const list = body.querySelector('.invoice-cards');
    if (!header || !create || !list) return result;
    header.querySelector('h3').textContent = 'Invoices & payments';
    const payable = [...body.querySelectorAll('[data-payment-invoice]')];
    const accepted = Boolean(state.currentPortal?.quote || (r.invoices||[]).some(i=>i.accepted_quote_invoice));
    header.querySelector('p').textContent = payable.length
      ? 'Record received payments against the existing invoice. Cash and bank transfer are supported.'
      : accepted ? 'View the accepted invoice and its payment history below.' : 'Accepting a quote creates its invoice automatically.';
    const other = document.createElement('details');other.className='v879-payment-actions';
    const summary = document.createElement('summary');summary.textContent='Other payment actions';
    const hint = document.createElement('p');hint.textContent='Create a separate invoice only when you need one. For changes to an accepted package, use Amend invoice on its existing invoice.';
    other.append(summary,hint,create);list.after(other);
    create.textContent='Create separate invoice';create.classList.remove('primary');create.classList.add('secondary');
    if (payable.length) {
      const action=document.createElement('button');action.type='button';action.className='primary v879-record-payment';
      action.textContent=payable.length===1?'Record payment':'Choose invoice to record payment';
      action.onclick=()=>{if(payable.length===1){const fold=payable[0].closest('details');if(fold)fold.open=true;payable[0].click()}else{payable[0].scrollIntoView({block:'center',behavior:'smooth'});payable[0].focus({preventScroll:true})}};
      header.append(action);
    }
    payable.forEach(button=>{button.textContent='Record payment';button.classList.add('primary');button.classList.remove('secondary')});
    // Keep old financial records accessible without competing with the payable invoice.
    const history=[...list.querySelectorAll('.invoice-card')].filter(card=>!card.querySelector('[data-payment-invoice]'));
    if(history.length){const fold=document.createElement('details');fold.className='v879-invoice-history';fold.open=!payable.length;const heading=document.createElement('summary');heading.textContent=`Paid & closed invoices (${history.length})`;fold.append(heading,...history);list.append(fold)}
    const empty=list.querySelector('.empty');if(empty){empty.replaceChildren();const title=document.createElement('strong');title.textContent='No invoices yet';const text=document.createElement('p');text.textContent=accepted?'No invoice is available here. Check the accepted quote before creating another invoice.':'Prepare and send the quote first. Its invoice appears here after the couple accepts.';empty.append(title,text)}
    return result;
  };
  function decorate(r){
    const drawer=document.querySelector('#drawer');if(!r||state.current?.id!==r.id||!drawer)return;
    // Imported records get familiar navigation wording only; all protected controls remain intact.
    if(r.brand==='wbm'&&r.kind==='wedding'&&r.legacy_source==='studio_ninja'){
      for(const [tab,label]of [['Journey','Quote & paperwork'],['Emails','Messages'],['Activity','Notes']]){const title=drawer.querySelector(`[data-tab="${tab}"] strong`);if(title)title.textContent=label}
    }
    if(!native(r))return;
    // Two controls previously led to the same client area. Retain the main bound control.
    const duplicate=drawer.querySelector('#record-portal-shortcut');if(duplicate)duplicate.hidden=true;
    const main=drawer.querySelector('#record-client-area');if(main)main.textContent='View couple’s quote & client area';
    // Keep exceptional administration behind a fold, retaining every original node and handler.
    const menu=drawer.querySelector('#record-actions-menu');
    if(menu&&!menu.querySelector('.v879-record-admin')){
      const fold=document.createElement('details');fold.className='v879-record-admin';
      const summary=document.createElement('summary');summary.textContent='Other booking actions';fold.append(summary);
      for(const selector of ['.record-primary-actions','#archive-record','.record-safety-actions']){const node=menu.querySelector(selector);if(node)fold.append(node)}
      menu.append(fold);
    }
  }
  const oldSelect=selectRecordTab;
  selectRecordTab=async function(r,...args){const result=await oldSelect.call(this,r,...args);decorate(r);return result};
  const oldOpen=openDrawer;
  openDrawer=async function(...args){const result=await oldOpen.apply(this,args);decorate(state.current);return result};
})();
