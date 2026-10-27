/* Isolated browser regression: every request is fulfilled locally. No real records or emails. */
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'../app/static');
const clone=x=>JSON.parse(JSON.stringify(x));
const bank={id:'primary',label:'Example account',account_name:'Example business',sort_code:'123456',account_number:'12345678'};
const alternate={...bank,id:'alternate',label:'New example account',account_number:'87654321'};
const catalog={packages:[{id:'package-example',code:'bronze',name:'Example package',price:475,deposit_amount:150,description:'Example photography package',eligible_package_codes:[]}],addons:[{id:'extra-example',name:'Example album',price:100,is_discount:false,eligible_package_codes:[]},{id:'discount-example',name:'Example discount',price:50,is_discount:true,eligible_package_codes:[]}]};
const offer={id:'offer-example',name:'Private template name',package_ids:['package-example'],optional_addon_ids:['extra-example'],required_addons:[],discounts:[{addon_id:'discount-example',name:'Example discount',price:50}],bank_account_id:'alternate',subject:'Your example wedding quote',body:'Hi {client_first_name}, here are your options.'};
const baseRecord={id:'example',brand:'wbm',kind:'wedding',status:'enquiry',title:'Example & Partner',client:{id:'example-client',first_name:'Example',last_name:'Couple',partner_name:'Partner',email:'example@example.com',phone:'07700900111'},event_date:'2027-08-20',venue_or_project:'Example Hall',quoted_total:0,deposit_amount:150,invoices:[],tasks:[],documents:[],quotes:[],notes:'Example private note',activity:[],booking_notes:[],workflow_state:{},form_data:{},legacy_source:null};
const basePortal={quote:null,quote_preparation:{prepared:false,package_ids:['package-example'],optional_addon_ids:['extra-example'],required_addons:[],discounts:[]},contract:null,submissions:[],emails:[],email_templates:[],quote_followups:[],final_timings:{available:false,submitted:false,template:{sections:[],fields:[]},coverage:{}},final_details_unlocked:false};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.WBM_TEST_CHROME||'/tmp/wbm-browser/chrome-linux/headless_shell',args:['--no-sandbox']});
 try{
 const p=await browser.newPage({viewport:{width:390,height:844},colorScheme:'light'});
 let record=clone(baseRecord),portal=clone(basePortal),calls=[],writes=[],errors=[];
 p.on('pageerror',e=>errors.push(e.stack));
 p.on('console',m=>{if(m.type()==='error'&&m.text().includes('TypeError'))console.log(m.text());});
 await p.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url()),key=url.pathname;calls.push(req.method()+' '+key+url.search);
  if(req.method()!=='GET'){
   const data=req.postDataJSON();writes.push({method:req.method(),key,data});
   if(key.endsWith('/quote/preparation')){portal.quote_preparation={...data,prepared:true};return route.fulfill({json:{ok:true}});}
   if(key.endsWith('/quote/send')){portal.emails=[{template_key:'quote',status:'sent',sent_at:'2026-10-18T12:00:00Z',subject:data.subject}];return route.fulfill({json:{url:'/client/example-only',email_sent:true}});}
   return route.abort();
  }
  if(key.startsWith('/api/')){
   let data={};
   if(key==='/api/auth/me')return route.fulfill({status:401,json:{detail:'Local fixture only'}});
   if(key==='/api/bookings/'+record.id)data=record;
   else if(key.endsWith('/portal'))data=portal;
   else if(key.endsWith('/conversation')){
    assert(Number(url.searchParams.get('limit'))>=10,'Conversation request must pass server validation');
    data={client_name:record.title,client_email:record.client.email,client_emails:[record.client.email],messages:[1,2,3,4].map(n=>({id:String(n),subject:'Example message '+n,date:`2026-10-${10+n}T12:00:00Z`,direction:n===4?'received':'sent',brand:'wbm',uid:'fixture'+n,body:'Example',attachments:[]}))};
   }
   else if(key.endsWith('/email-centre'))data={recipient:record.client.email,client_name:record.title,templates:[{template_key:'quote',display_name:'Quote email',subject:'Standard subject',body:'Standard wording'}],quote_email:{subject:offer.subject,body:offer.body}};
   else if(key.endsWith('/quote-preview-data'))data={catalog:clone(catalog),quote_preparation:portal.quote_preparation,preview_bank:alternate};
   else if(key==='/api/catalog')data=catalog;
   else if(key==='/api/quote-templates')data=[offer];
   else if(key==='/api/quote-bank-accounts')data=[bank,alternate];
   else if(key.endsWith('/original-enquiry'))data={source:'website_submission',answers:{message:'An example enquiry, never saved to a server.'}};
   else if(key==='/api/bookings')data=[record];
   else if(key==='/api/dashboard')data={upcoming:[],tasks:[]};
   else if(key==='/api/businesses')data=[{brand:'wbm',bank_details:bank}];
   else if(/queues/.test(key))data={queues:{},upcoming:[]};
   else if(/form/.test(key))data={fields:[],sections:[]};
   else if(/tasks|documents|invoices|blocks|jobs|activity/.test(key))data=[];
   return route.fulfill({json:data});
  }
  const f=key==='/'?path.join(root,'index.html'):key.startsWith('/static/')?path.join(root,path.basename(key)):null;
  if(f&&fs.existsSync(f)){
   const ct=f.endsWith('.js')?'application/javascript':f.endsWith('.css')?'text/css':'text/html';
   let body=fs.readFileSync(f);if(f.endsWith('v844.js'))body=body.toString().replace('} catch (error) {','} catch (error) { console.error(error.stack);');
   return route.fulfill({contentType:ct,body});
  }
  return route.abort();
 });
 await p.goto('https://isolated-wbm.invalid/');await p.locator('#login').waitFor();await p.waitForTimeout(300);
 await p.evaluate(({r,b})=>{state.records=[r];state.businesses=[{brand:'wbm',bank_details:b}];showApp();}, {r:record,b:bank});
 async function open(){calls=[];await p.evaluate(id=>openDrawer(id),record.id);await p.locator('.v866-board').waitFor();await p.waitForTimeout(100);}
 await open();
 assert.equal(calls.filter(c=>c.endsWith('/portal')).length,1,'Opening native overview should fetch portal once');
 assert.equal(calls.filter(c=>c.includes('/conversation')).length,1);
 assert.deepEqual(await p.locator('[data-v866-mail] strong').allTextContents(),['Example message 4','Example message 3','Example message 2']);
 assert.equal(await p.locator('.v872-fold:not([open]) [data-v866-action=timings]').count(),1);
 await p.locator('.v878-original-text').filter({hasText:'An example enquiry'}).waitFor();
 assert.equal(await p.locator('.v878-original').count(),1);
 assert((await p.locator('.v872-board').boundingBox()).y<500,'Useful booking content should start within first phone screen');
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await p.screenshot({path:'/tmp/v872-mobile-light.png'});
 // Focused workflow: inline original, exact recent message and independent document panes.
 assert((await p.locator('#drawer-body').boundingBox()).y<350,'Compact header must expose content sooner');
 assert.equal(writes.length,0);
 await p.locator('[data-v866-mail] button').first().click();
 await p.waitForFunction(()=>document.querySelector('[data-conversation-message="4"]')?.open);
 assert.equal(await p.locator('.couple-conversation-list > details').first().getAttribute('data-conversation-message'),'4');
 assert.equal(await p.locator('[data-conversation-message="4"]').getAttribute('open'),'');
 await p.evaluate(()=>{window.fixtureOriginalReply=window.openInboxMessageFromDashboard;window.fixtureReply=null;window.openInboxMessageFromDashboard=(brand,uid)=>window.fixtureReply=[brand,uid]});
 await p.locator('[data-conversation-message="4"] .v878-reply').click();assert.deepEqual(await p.evaluate(()=>window.fixtureReply),['wbm','fixture4']);
 await p.evaluate(()=>window.openInboxMessageFromDashboard=window.fixtureOriginalReply);

 await p.locator('[data-tab="Paperwork"]').click();await p.waitForFunction(()=>document.querySelector('#drawer-body')?.dataset.v878Pane==='paperwork'&&document.querySelector('.v811-journey-quote')?.closest('.v855-fold')?.classList.contains('v878-inactive-pane'));assert(await p.locator('.v811-journey-forms').isVisible());assert(!(await p.locator('.v811-journey-quote').isVisible()));
 await p.locator('.v878-paperwork-tools [data-v878-pane="timings"]').click();assert(await p.locator('.v820-final').isVisible());assert(!(await p.locator('.v811-journey-forms').isVisible()));
 await p.locator('.v878-paperwork-tools [data-v878-pane="call"]').click();assert(await p.locator('.v823-final-call-pack').isVisible());

 await p.locator('[data-tab="Journey"]').click();await p.waitForFunction(()=>document.querySelector('#drawer-body')?.dataset.v878Pane==='quote'&&document.querySelector('.v811-journey-quote')?.closest('.v855-fold')?.open);assert(await p.locator('.v811-journey-quote').isVisible());assert(!(await p.locator('.v820-final').isVisible()));
 await p.evaluate(()=>WBMLayoutV855.reveal(document.querySelector('.v811-journey-forms')));assert(await p.locator('.v811-journey-forms').isVisible());
 await p.evaluate(()=>selectRecordTab(state.current,'Overview'));
 assert.equal(writes.length,0,'Reading and navigating cannot save or send');
 await p.locator('#record-more').click();assert.equal(await p.locator('#record-actions-menu [data-v861-enquiry]').count(),1);
 await p.locator('#record-actions-menu [data-wbm-appearance]').selectOption('dark');assert.equal(await p.locator('html').getAttribute('data-wbm-theme'),'dark');
 await p.locator('#record-more').click();
 await p.locator('.v878-original button').click();await p.waitForFunction(()=>document.querySelector('.v861-paper')?.textContent.includes('An example enquiry'));assert((await p.locator('.v861-paper').innerText()).includes('An example enquiry'));await p.locator('#close-modal').click();
 await p.locator('[data-v866-action=quote]').click();await p.locator('#v857-offer-choice').waitFor();
 await p.locator('#v857-offer-choice').selectOption(offer.id);assert.equal(await p.locator('#offer-bank').inputValue(),'alternate');
 assert.equal(await p.locator('.v878-customise').getAttribute('open'),null,'Named template starts as a concise summary');
 assert((await p.locator('#v878-offer-summary').innerText()).includes('£425.00'));
 await p.screenshot({path:'/tmp/v878-template-mobile-dark.png'});
 await p.locator('.v878-customise > summary').click();
 await p.locator('[data-v857-price="offer-discount-discount-example"]').fill('75');assert((await p.locator('#v878-offer-summary').innerText()).includes('£400.00'));
 await p.locator('[data-v857-price="offer-discount-discount-example"]').fill('50');assert((await p.locator('#v878-offer-summary').innerText()).includes('£425.00'));
 assert.equal(writes.length,0,'Customisation is local until the existing save button is pressed');

 await p.locator('#dynamic-form footer .primary').click();await p.locator('.v858-summary').waitFor();
 assert.equal(await p.locator('#quote-email-subject').inputValue(),offer.subject);
 await p.locator('#v857-email-choice').selectOption('email:quote');assert.equal(await p.locator('#quote-email-subject').inputValue(),'Standard subject');await p.locator('#v857-email-choice').selectOption('');assert.equal(await p.locator('#quote-email-subject').inputValue(),offer.subject);
 assert.equal(await p.locator('#v857-email-choice option').filter({hasText:'Private template name'}).count(),0);
 assert((await p.locator('.v858-summary').innerText()).includes('New example account'));
 assert.equal(writes.length,1);assert.deepEqual(writes[0].data,{package_ids:offer.package_ids,optional_addon_ids:offer.optional_addon_ids,required_addons:[],discounts:[{addon_id:'discount-example',price:50}],bank_account_id:'alternate',email_subject:offer.subject,email_body:offer.body});
 await p.locator('#close-modal').click();
 // A prepared quote must not imply it has already been sent.
 await p.evaluate(()=>WBMReview.viewQuote(state.current));await p.locator('.v861-paper').waitFor();await p.waitForFunction(()=>document.querySelector('.v861-paper')?.textContent.includes('not sent to the couple'));assert((await p.locator('.v861-paper').innerText()).includes('not sent to the couple'));await p.locator('#close-modal').click();
 // Exercise explicit sending against a local fake endpoint only.
 await p.evaluate(()=>reviewAndSendQuoteEmail(state.current,document.querySelector('#drawer-body')));await p.locator('.v858-summary').waitFor();await p.locator('#dynamic-form footer .primary').click();await p.locator('#modal').waitFor({state:'hidden'});
 assert.equal(writes.length,2);assert.equal(writes[1].key,'/api/bookings/example/quote/send');assert.equal(writes[1].data.subject,offer.subject);
 await p.evaluate(()=>WBMReview.viewQuote(state.current));await p.waitForFunction(()=>document.querySelector('.v861-paper')?.textContent.includes('Quote sent'));assert((await p.locator('.v861-paper').innerText()).includes('Quote sent'));await p.locator('#close-modal').click();
 // Returning to Overview refreshes server facts; the initial load is not a lasting cache.
 await p.evaluate(()=>selectRecordTab(state.current,'Overview'));assert.equal(calls.filter(c=>c.endsWith('/portal')).length>1,true);
 assert.equal(await p.locator('#record-actions-menu [data-v861-enquiry]').count(),1,'No duplicate shortcuts after tab changes');
 // Completed paperwork folds away, but new review work stays prominent.
 record={...clone(baseRecord),invoices:[{id:'invoice-example',number:'EXAMPLE-ONLY',status:'part_paid',total:475,paid:150,balance:325,line_items:[{name:'Example package',total:475}],payments:[{id:'payment-example',amount:150,paid_date:'2026-10-18',payment_type:'bank_transfer'}]}],status:'confirmed',deposit_paid_date:'2026-10-18',quoted_total:475,tasks:[{id:'review',title:'Review timings',workflow_key:'wbm_review_final_timings',completed:false}]};
 portal={...clone(basePortal),quote:{status:'accepted',total:475,deposit_amount:150,line_items:[{name:'Example package',total:475}],accepted_at:'2026-10-17T12:00:00Z'},submissions:[{id:'booking-form',form_type:'booking_form',data:{},submitted_at:'2026-10-17T12:00:00Z'},{id:'timings-form',form_type:'final_timings',data:{},submitted_at:'2026-10-18T12:00:00Z'}],contract:{accepted_at:'2026-10-17T12:00:00Z',supplier_signed_at:'2026-10-17T13:00:00Z',fully_signed:true},emails:[{template_key:'contract_completed',status:'sent',sent_at:'2026-10-17T14:00:00Z'}]};
 await open();assert.equal(await p.locator('.v872-fold:not([open]) [data-v866-action=agreement]').count(),1);
 assert.equal(await p.locator('.v866-panel > .v866-doc [data-v866-action=timings]').count(),1);
 for(const tab of ['Quote','Paperwork','Emails','Payments','Files','Activity','Overview']){await p.evaluate(tab=>selectRecordTab(state.current,tab),tab);await p.waitForTimeout(60);assert.equal(await p.locator('.v844-section-error').count(),0,'Section error: '+tab);}
 for(const width of [320,390,768,1280])for(const theme of ['light','dark']){
  await p.setViewportSize({width,height:900});
  await p.evaluate(theme=>{const field=document.querySelector('#drawer [data-wbm-appearance]');field.value=theme;field.dispatchEvent(new Event('change',{bubbles:true}))},theme);
  for(const tab of ['Quote','Paperwork','Emails','Payments','Files','Activity','Overview']){
   await p.evaluate(tab=>selectRecordTab(state.current,tab),tab);await p.waitForTimeout(40);
   assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Page overflow ${width}/${theme}/${tab}`);
   assert.equal(await p.locator('.v844-section-error').count(),0,`Section failed ${width}/${theme}/${tab}`);
   assert.equal(await p.locator('#record-actions-menu [data-v861-enquiry]').count(),1);
   if(width===390&&tab==='Paperwork'){await p.locator('#drawer').evaluate(el=>el.scrollTo(0,0));await p.screenshot({path:`/tmp/v878-paperwork-mobile-${theme}.png`})}
  }
 }
 await p.locator('#drawer').evaluate(el=>el.scrollTo(0,0));await p.screenshot({path:'/tmp/v872-desktop-dark.png'});
 // Imported records must retain the original interface and blocked general automation.
 record={...clone(baseRecord),id:'imported-example',legacy_source:'studio_ninja',automation_suppressed:true};portal=clone(basePortal);
 await p.evaluate(id=>openDrawer(id),record.id);assert.equal(await p.locator('.v872-board').count(),0);assert.equal(await p.locator('#drawer.v866-workspace').count(),0);assert((await p.locator('#drawer').innerText()).includes('protected'));
 assert.equal(writes.length,2,'Navigation must never write enquiries, bookings, payments, agreements or settings');
 assert.deepEqual(errors,[]);console.log('PASS: isolated native/imported fixtures; mobile 320/390/768 and desktop; themes; single initial portal request; recent messages; document grouping; unchanged quote payload/bank/discount; explicit fake send; all sections; no navigation writes.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

