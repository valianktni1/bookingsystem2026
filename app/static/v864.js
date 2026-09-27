/* V8.64: presentation only; existing action handlers and safeguards are retained. */
(() => {
  'use strict';
  const native=r=>window.WBMSetup?.native(r);
  function fold(node,title,open=false){
    if(!node||node.parentElement?.classList.contains('v864-fold'))return null;
    const box=document.createElement('details');box.className='v864-fold';box.open=open;
    const summary=document.createElement('summary');summary.textContent=title;
    node.before(box);box.append(summary,node);return box;
  }
  function finishedFollowups(portal){
    const rows=portal?.quote_followups||[];
    return Boolean(portal?.quote?.status==='accepted'||rows.length&&rows.every(row=>['sent','not_needed'].includes(row.status)));
  }
  function messages(r,body){
    if(!native(r))return;
    const root=body.querySelector('.v842-email-workspace');if(!root||root.dataset.v864)return;
    root.dataset.v864='1';
    const conversation=root.querySelector('[data-couple-conversation]');
    const heading=root.querySelector('.v842-email-head');
    if(conversation&&heading)heading.after(conversation);
    const stats=root.querySelector('.v842-email-stats');
    const delivery=stats&&fold(stats,'Email delivery details');
    if(delivery){
      // Move whole existing folds so their bound controls remain intact.
      for(const selector of ['.workflow-email-proof','.v842-email-log']){
        const node=root.querySelector(selector);if(node)delivery.append(node.closest('.v855-fold')||node);
      }
      root.append(delivery);
      const failed=recordJourneyFacts(r,state.currentPortal||{}).failedEmail;
      if(failed){delivery.open=true;delivery.querySelector('summary').textContent='Email delivery details · sending issue needs attention';}
    }
    const followups=root.querySelector('.v843-followups');
    if(finishedFollowups(state.currentPortal))fold(followups,'Previous quote follow-ups');
    const help=root.querySelector('.v842-email-head p');
    if(help)help.textContent='Read and reply to the couple here. Sending records and quote follow-ups are below.';
  }
  function activity(r,body){
    if(!native(r)||body.querySelector('.v864-filters'))return;
    const timeline=body.querySelector('.v811-timeline');if(!timeline)return;
    const rows=[...timeline.querySelectorAll('.v811-timeline-event')];
    const nav=document.createElement('nav');nav.className='v864-filters';nav.setAttribute('aria-label','Filter booking activity');
    const count=document.createElement('p');count.className='v864-filter-count';count.setAttribute('aria-live','polite');
    const empty=document.createElement('p');empty.className='v864-empty';empty.textContent='No activity in this category.';empty.hidden=true;
    const matches=(row,key)=>key==='all'||key==='notes'&&row.classList.contains('note')||key==='changes'&&row.classList.contains('audit')||key==='emails'&&(row.classList.contains('sent')||row.classList.contains('failed'));
    for(const [key,label] of [['all','All'],['notes','Notes'],['changes','Booking changes'],['emails','Emails']]){
      const button=document.createElement('button');button.type='button';button.dataset.filter=key;
      button.textContent=`${label} (${rows.filter(row=>matches(row,key)).length})`;
      button.onclick=()=>{let visible=0;rows.forEach(row=>{row.hidden=!matches(row,key);if(!row.hidden)visible++;});nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));count.textContent=`${visible} of ${rows.length} events`;empty.hidden=visible!==0;};
      nav.append(button);
    }
    timeline.before(nav,count);timeline.after(empty);nav.firstElementChild.click();
  }
  function header(r){
    const drawer=document.querySelector('#drawer');if(!drawer)return;
    drawer.classList.toggle('v864-native',Boolean(native(r)));if(!native(r))return;
    const nav=drawer.querySelector('.record-contact-actions'),menu=drawer.querySelector('#record-actions-menu');if(!nav||!menu)return;
    const mobile=matchMedia('(max-width:650px)').matches;
    if(mobile){
      nav.querySelectorAll('a[href^="tel:"],a.directions-link,a[target="_blank"]').forEach(node=>{node.dataset.v864Moved='1';menu.append(node);});
    }else menu.querySelectorAll('[data-v864-moved]').forEach(node=>{delete node.dataset.v864Moved;nav.append(node);});
  }
  const oldMessages=renderBookingEmails;
  renderBookingEmails=function(r,body){const result=oldMessages(r,body);messages(r,body);return result;};
  const oldRender=renderTab;
  renderTab=async function(r,tab,target=null){const result=await oldRender(r,tab,target);if(normaliseRecordTab(tab)==='Activity')activity(r,target||document.querySelector('#drawer-body'));return result;};
  const oldSelect=selectRecordTab;
  selectRecordTab=async function(r,...args){const result=await oldSelect(r,...args);header(r);return result;};
  window.addEventListener('resize',()=>header(state.current));
  window.WBMTidyV864={finishedFollowups};
})();
