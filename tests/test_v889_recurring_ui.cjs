/* Form and schedule interactions against mocked APIs; no live account or email. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../app/static');
const flush=()=>new Promise(r=>setImmediate(r));
const settle=async()=>{for(let i=0;i<5;i++)await flush();};
const input=(w,selector,value,event='input')=>{const el=w.document.querySelector(selector);assert(el,selector);el.value=value;el.dispatchEvent(new w.Event(event,{bubbles:true}));};
(async()=>{
 const dom=new JSDOM('<div id="page-eyebrow"></div><h1 id="page-title"></h1><p id="page-subtitle"></p><main id="content"></main>',{url:'https://example.test/ivoryquotes',runScripts:'outside-only'});
 const w=dom.window;w.structuredClone=structuredClone;
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
 w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
 let rows=[],calls=[],emails=[],plans=[{id:'plan-1',booking_id:'booking-1',customer:'Example Business',title:'SEO',status:'active',cycle_total:650,interval_months:12,start_date:'2030-01-31',next_billing_date:'2031-01-31',next_cycle:1,due_days:0,terms:'Agreed terms',description:'Agreed SEO',last_error:null,invoices:[{id:'invoice-1',number:'WBM02001',status:'unpaid',balance:650,period_start:'2030-01-31',period_end:'2031-01-30'}]}];
 w.eval('var state={view:"ivoryquotes"}; var render=()=>{};');w.toast=()=>{};w.openDrawer=()=>{};w.emailInvoice=id=>emails.push(id);
 w.api=async(url,opts={})=>{
   const body=opts.body?JSON.parse(opts.body):null;calls.push({url,method:opts.method||'GET',body});
   if(url.endsWith('/projects'))return [];
   if(url==='/api/ivory-quotes'&&!body)return rows;
   if(url==='/api/ivory-quotes'&&body){const d=body.details;const r={id:'q1',booking_id:'booking-1',reference:'IDQ-TEST-R1',status:'draft',details:d,total:0,monthly:60,invoice:null,billing:{...d.billing,cycle_total:d.billing.cycle_total||String(60*d.billing.interval_months)}};rows=[r];return r;}
   if(url==='/api/ivory-recurring')return plans;
   if(url==='/api/ivory-recurring/plan-1'&&opts.method==='PUT'){assert.equal(body.confirmed,true);plans[0]={...plans[0],title:body.title,cycle_total:Number(body.cycle_total),description:body.description,terms:body.terms};return plans[0];}
   if(url==='/api/ivory-recurring/plan-1/action'){plans[0].status=body.action==='pause'?'paused':body.action==='resume'?'active':'cancelled';return plans[0];}
   throw Error('Unexpected API '+url);
 };
 w.eval(fs.readFileSync(path.join(root,'ivory-quotes.js'),'utf8'));w.eval('render()');await settle();
 w.document.querySelector('[data-recurring-new]').click();await settle();
 assert.equal(w.document.querySelector('[name=kind]').value,'monthly');
 input(w,'[name=amount]','60');input(w,'[name=name]','SEO');input(w,'[name=description]','Editable customer scope');
 for(const months of [1,3,6,12]){input(w,'[name=billing_interval]',String(months),'change');assert.match(w.document.querySelector('[data-billing-summary]').textContent,new RegExp('£'+60*months));}
 input(w,'[name=billing_total]','650');assert.match(w.document.querySelector('[data-billing-summary]').textContent,/£650/);
 input(w,'[name=billing_interval]','0','change');assert.equal(w.document.querySelector('[data-billing]').hidden,true);assert.equal(w.document.querySelector('[name=billing_start]').disabled,true);
 input(w,'[name=billing_interval]','12','change');assert.equal(w.document.querySelector('[data-billing]').hidden,false);
 input(w,'[name=title]','Annual SEO');input(w,'[name=customer]','Example Business');input(w,'[name=email]','example@example.com');input(w,'[name=billing_start]','2030-01-31');
 w.document.querySelector('dialog form').dispatchEvent(new w.Event('submit',{cancelable:true}));await settle();
 const saved=calls.find(c=>c.method==='POST'&&c.url==='/api/ivory-quotes').body.details;
 assert.deepEqual(saved.billing,{interval_months:12,start_date:'2030-01-31',due_days:0,cycle_total:'650'});
 assert.equal(saved.lines[0].description,'Editable customer scope');assert.equal(emails.length,0);
 w.document.querySelector('[data-schedules]').click();await settle();assert.match(w.document.querySelector('dialog').textContent,/WBM02001/);
 w.document.querySelector('[data-action=edit]').click();await settle();input(w,'[name=total]','700');input(w,'[name=description]','Changed future scope');
 w.document.querySelector('dialog form').dispatchEvent(new w.Event('submit',{cancelable:true}));await settle();assert.equal(plans[0].cycle_total,700);
 w.document.querySelector('[data-action=pause]').click();await settle();w.document.querySelector('[data-confirm]').click();await settle();assert.equal(plans[0].status,'paused');
 w.document.querySelector('[data-action=resume]').click();await settle();w.document.querySelector('[data-confirm]').click();await settle();assert.equal(plans[0].status,'active');assert.equal(emails.length,0);
 dom.window.close();
 // Customer sees the exact billing commitment, then a future-start confirmation.
 const client=new JSDOM('<main><section id="quote"></section></main>',{url:'https://example.test/ivory-quote/token',runScripts:'outside-only'});
 const cw=client.window;let accepted=false;
 cw.fetch=async(url,opts)=>{if(opts?.method==='POST'){accepted=true;return {ok:true,json:async()=>({ok:true,number:null})};}return {ok:true,json:async()=>({...rows[0],status:accepted?'accepted':'shared',recurring:accepted?plans[0]:null})};};
 cw.eval(fs.readFileSync(path.join(root,'ivory-quote-client.js'),'utf8'));await settle();
 assert.match(cw.document.querySelector('#quote').textContent,/£650.00 every 12 month/);
 assert.match(cw.document.querySelector('label.iq-check').textContent,/recurring billing frequency/);
 input(cw,'[name=name]','Example Customer');cw.document.querySelector('form').dispatchEvent(new cw.Event('submit',{cancelable:true}));await settle();
 assert.match(cw.document.querySelector('#quote').textContent,/service is scheduled/);assert.equal(cw.document.querySelector('a'),null);
 cw.close();console.log('Recurring quote fields, all intervals, custom price, future edits, pause/resume and client acceptance passed.');
})().catch(e=>{console.error(e);process.exit(1);});
