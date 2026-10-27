/* Focused native-booking presentation. Existing write/send/payment handlers remain authoritative. */
(() => {
 'use strict';
 const native=r=>r?.brand==='wbm'&&r.kind==='wedding'&&!r.legacy_source;
 const pendingMessages=new Map();
 let panes={};try{const saved=JSON.parse(sessionStorage.getItem('wbm-workspace-panes-v878')||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))panes=saved}catch(_){}
 const allowed=new Set(['quote','paperwork','timings','call']);
 const pane=r=>allowed.has(panes[r.id])?panes[r.id]:state.currentPortal?.quote?'paperwork':'quote';
 function remember(r,value){if(!native(r)||!allowed.has(value))return;panes[r.id]=value;try{sessionStorage.setItem('wbm-workspace-panes-v878',JSON.stringify(Object.fromEntries(Object.entries(panes).slice(-50))))}catch(_){}}
 function applyPane(r,body=document.querySelector('#drawer-body')){
  if(!native(r)||!body||state.current?.id!==r.id)return;
  const mode=pane(r);body.dataset.v878Pane=mode;
  const entries=[['.v811-journey-quote','quote'],['.v811-journey-forms','paperwork'],['.v820-final','timings'],['.v823-final-call-pack','call']];
  for(const [selector,key]of entries){const node=body.querySelector(selector);if(!node)continue;const box=node.closest('.v855-fold')||node;if(box!==node)node.classList.remove('v878-inactive-pane','v878-selected-pane');box.classList.toggle('v878-inactive-pane',key!==mode);box.classList.toggle('v878-selected-pane',key===mode);if(key===mode&&box.tagName==='DETAILS')box.open=true;}
  body.querySelectorAll('.v855-jump,.v863-progress').forEach(el=>el.classList.add('v878-redundant'));
  const root=body.querySelector('.v811-journey');
  if(root&&!root.querySelector('.v878-paperwork-tools')){
   const tools=document.createElement('nav');tools.className='v878-paperwork-tools';tools.setAttribute('aria-label','Paperwork to view');
   for(const [key,label]of [['paperwork','Booking form & agreement'],['timings','Final timings'],['call','Final call']]){const button=document.createElement('button');button.type='button';button.dataset.v878Pane=key;button.textContent=label;button.onclick=()=>{remember(r,key);applyPane(r,body);decorate(r)};tools.append(button)}
   root.prepend(tools);
  }
  const tools=root?.querySelector('.v878-paperwork-tools');if(tools){tools.hidden=mode==='quote';tools.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.v878Pane===mode)))}
 }
 function decorate(r){
  const drawer=document.querySelector('#drawer');if(!drawer||state.current?.id!==r?.id)return;
  drawer.classList.toggle('v878-flow',native(r));if(!native(r))return;
  const back=drawer.querySelector('#close-drawer');if(back&&!back.dataset.v878){back.dataset.v878='1';back.innerHTML='<span>←</span> Back';back.setAttribute('aria-label','Back to the booking list')}
  const email=drawer.querySelector('#record-email-client-top');if(email){email.textContent='Email';email.setAttribute('aria-label','Email '+r.title);email.classList.remove('primary');email.classList.add('secondary')}
  const more=drawer.querySelector('#record-more');if(more)more.innerHTML='More <span aria-hidden="true">⌄</span>';
  const step=drawer.querySelector('.record-next-action'),help=step?.querySelector(':scope > div > span');
  if(help&&!step.querySelector('.v878-step-help')){const details=document.createElement('details');details.className='v878-step-help';details.open=!matchMedia('(max-width:820px)').matches;const summary=document.createElement('summary');summary.textContent='About this step';help.before(details);details.append(summary,help);if(matchMedia('(max-width:820px)').matches){details.open=false;drawer.querySelector('#record-actions-menu')?.append(details)}}
  const next=drawer.querySelector('#next-record-action');if(next&&!next.onclick?.v878Wrapped){const previous=next.onclick;next.onclick=function(event){const action=recordNextAction(r,state.currentPortal||{}).action;if(['review_forms','review_booking_form','countersign','review_agreement','review_confirmation'].includes(action))remember(r,'paperwork');else if(['send_quote','view_quote','review_quote'].includes(action))remember(r,'quote');return previous?.call(this,event)};next.onclick.v878Wrapped=true;const action=recordNextAction(r,state.currentPortal||{}).action;if(action==='send_quote')next.textContent='Prepare quote';if(action==='review_forms')next.textContent='View paperwork'}
  const notes=drawer.querySelector('[data-tab="Activity"] strong');if(notes)notes.textContent='Notes';
  const quote=drawer.querySelector('[data-tab="Journey"]');if(!quote)return;
  quote.querySelector('strong').textContent='Quote';quote.onclick=()=>selectRecordTab(r,'Quote',true);
  const portal=state.currentPortal||{},facts=recordJourneyFacts(r,portal),setup=window.WBMSetup.progress(r,portal);const quoteMeta=quote.querySelector('small');if(quoteMeta)quoteMeta.textContent=portal.quote?'Accepted':facts.quoteSent?'Sent':portal.quote_preparation?.prepared?'Prepared':'Not prepared';
  let paperwork=drawer.querySelector('[data-tab="Paperwork"]');
  if(!paperwork){paperwork=quote.cloneNode(true);paperwork.dataset.tab='Paperwork';paperwork.querySelector('strong').textContent='Paperwork';const icon=paperwork.querySelector('i');if(icon)icon.textContent='✓';quote.after(paperwork)}
  paperwork.onclick=()=>selectRecordTab(r,'Paperwork',true);
  const paperworkMeta=paperwork.querySelector('small');if(paperworkMeta)paperworkMeta.textContent=`${Number(setup.reviewed)+Number(setup.confirmed)}/2 reviewed & complete`;
  for(const b of [quote,paperwork]){const active=normaliseRecordTab(state.currentTab)==='Journey'&&(b===quote?pane(r)==='quote':pane(r)!=='quote');b.classList.toggle('active',active);b.setAttribute('aria-current',active?'page':'false')}
 }
 const oldOverview=renderOverview;
 renderOverview=function(r,body){const result=oldOverview.apply(this,arguments);if(!native(r)||state.currentPortal?.quote||!['enquiry','quoted'].includes(r.status))return result;
  const host=body.querySelector('.v866-left');if(!host)return result;
  const card=document.createElement('section');card.className='v866-panel v878-original';card.innerHTML='<header><h2>Original enquiry</h2><button type="button" class="secondary">All answers</button></header><div class="v878-original-text" role="status">Loading the original enquiry…</div>';
  host.prepend(card);card.querySelector('button').onclick=()=>window.WBMReview.viewEnquiry(r);
  // The message replaces the repeated generic View row; the exact full answers remain one tap away.
  const old=host.querySelector('[data-v866-action="enquiry"]')?.closest('.v866-doc');if(old)old.remove();
  const prepare=host.querySelector('[data-v866-action="quote"]');if(prepare){const previous=prepare.onclick;prepare.onclick=function(event){remember(r,'quote');return previous?.call(this,event)}}
  api(`/api/bookings/${r.id}/original-enquiry`).then(original=>{if(!card.isConnected)return;const target=card.querySelector('.v878-original-text');if(original.source==='website_submission'){const answers=original.answers||{};const message=answers.message||answers.enquiry_message||answers.additional_information;target.textContent=message?String(message):'Their original submission is saved. Open All answers to read the complete enquiry.'}else if(original.source==='saved_notification'){target.textContent=original.body||'The original enquiry notification is saved. Open All answers.'}else target.textContent='No original website submission is saved for this record. Open All answers for available source information.'}).catch(()=>{if(card.isConnected)card.querySelector('.v878-original-text').textContent='The original enquiry could not be loaded. Open All answers to retry.'});
  return result;
 };
 const oldRender=renderTab;
 renderTab=async function(r,tab,...args){
  const body=args[0]||document.querySelector('#drawer-body'),focused=native(r)&&normaliseRecordTab(tab)==='Journey';
  const observer=focused&&body?new MutationObserver(()=>applyPane(r,body)):null;
  if(observer)observer.observe(body,{childList:true,subtree:true});
  try{const pending=oldRender.call(this,r,tab,...args);if(focused)applyPane(r,body);const result=await pending;if(focused)applyPane(r,body);return result}finally{observer?.disconnect()}
 };
 const oldSelect=selectRecordTab;
 selectRecordTab=async function(r,tab,...args){if(native(r)){if(tab==='Paperwork'){remember(r,'paperwork');tab='Journey'}else if(tab==='Quote'){remember(r,'quote');tab='Journey'}}const result=await oldSelect.call(this,r,tab,...args);decorate(r);if(normaliseRecordTab(tab)==='Journey')applyPane(r);return result};
 const oldOpen=openDrawer;
 openDrawer=async function(id,...args){const result=await oldOpen.call(this,id,...args);decorate(state.current);return result};
 const layout=window.WBMLayoutV855;
 if(layout)window.WBMLayoutV855={...layout,reveal(node){const r=state.current;if(native(r)&&node){const key=node.closest('.v811-journey-quote')?'quote':node.closest('.v820-final')?'timings':node.closest('.v823-final-call-pack')?'call':node.closest('.v811-journey-forms')?'paperwork':null;if(key){remember(r,key);applyPane(r);decorate(r)}}return layout.reveal(node)}};
 const review=window.WBMReview;
 if(review){const direct=review.direct;review.direct=async function(r,action){if(native(r)&&['review_forms','review_booking_form','review_agreement','countersign','review_confirmation'].includes(action))remember(r,'paperwork');return direct.apply(this,arguments)}}
 async function openMessage(r,id){if(!native(r))return selectRecordTab(r,'Emails',true);pendingMessages.clear();pendingMessages.set(r.id,String(id));await selectRecordTab(r,'Emails',true)}
 function conversation(r,host,data){if(!native(r)||state.current?.id!==r.id||!host.isConnected)return;
  const list=host.querySelector('.couple-conversation-list');if(!list)return;
  const rows=[...list.querySelectorAll('[data-conversation-message]')];const ordered=[...(data.messages||[])].sort((a,b)=>String(b.date||'').localeCompare(String(a.date||''))||String(b.id||'').localeCompare(String(a.id||'')));
  const byId=new Map(rows.map(row=>[row.dataset.conversationMessage,row]));
  for(const message of ordered){const row=byId.get(String(message.id));if(!row)continue;list.append(row);if(message.direction==='received'&&message.brand&&message.uid){const button=document.createElement('button');button.type='button';button.className='secondary v878-reply';button.textContent='Reply to this email';button.onclick=()=>window.openInboxMessageFromDashboard(message.brand,message.uid);row.querySelector('.couple-message-body')?.append(button)}}
  const footer=host.querySelector('.couple-conversation > footer > span');if(footer)footer.textContent='Most recent messages first. Older mail may be available in Inbox. Other clients and personal emails are never included.';
  const id=pendingMessages.get(r.id);if(!id)return;pendingMessages.delete(r.id);const target=byId.get(id);
  if(target){target.hidden=false;target.open=true;target.classList.add('v878-message-focus');const summary=target.querySelector('summary');if(summary){summary.tabIndex=-1;summary.focus({preventScroll:true})}target.scrollIntoView({block:'center',behavior:'smooth'})}else{const notice=document.createElement('p');notice.className='conversation-notice';notice.textContent='That message is not in the currently loaded history. Open this couple in Inbox to look for it.';list.before(notice)}
 }
 window.WBMFlowV878={openMessage,conversation};
})();
