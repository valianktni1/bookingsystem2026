/* Read-only checks against the actual Payments renderer and its invoice wrappers. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const runtime=process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES||'C:/Users/Mark/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const {chromium}=require(path.join(runtime,'playwright'));
const root=path.resolve(__dirname,'..');
const pkg={type:'package',name:'Gold Package',description:'Includes a wedding album and full-day photography',quantity:1,unit_price:899,total:899};
const booth={type:'addon',code:'photobooth',name:'Photobooth after the wedding breakfast',quantity:1,unit_price:249,total:249};
const album={type:'addon',code:'album_offer',name:'Wedding album upgrade',quantity:1,unit_price:120,total:120};
const invoice=(id,lines,changes={})=>({id,number:'WBM02001',status:'paid',total:1268,paid:1268,balance:0,due_date:'2027-05-05',line_items:lines,payments:[],...changes});
const record=invoices=>({id:'example-booking',brand:'wbm',kind:'wedding',title:'Emma & James',package_name:'Gold Package',quoted_total:1268,invoices,workflow_state:{}});
const clone=value=>JSON.parse(JSON.stringify(value));
const cases=[
 {name:'accepted extras',record:record([invoice('i1',[pkg,booth,album])]),expected:[booth.name,album.name]},
 {name:'later extras and discounts',record:record([invoice('i1',[pkg,booth,{type:'discount',name:'Album discount',total:-50},{type:'addon',name:'Removed extra',total:-10},
  {type:'addon',name:'Parent albums',manual_amendment:true,quantity:2,unit_price:125,total:250},
  {type:'addon',name:'Complimentary extra hour',quantity:1,total:0}])]),expected:[booth.name,'Parent albums','Complimentary extra hour']},
 {name:'included package features are not extras',record:record([invoice('i1',[pkg])]),expected:[]},
 {name:'untyped imported items',record:{...record([invoice('i1',[{name:'Gold Package',total:899},{name:'Photo booth',total:'£249.00'},{name:'Album',quantity:2,unit_price:'75.00'}])]),legacy_source:'studio_ninja'},expected:['Photo booth','Album']},
 {name:'generic imported service lines',record:{...record([invoice('i1',[{type:'service',name:'Gold Package',total:899},{type:'service',name:'Parent albums',qty:2,rate:75},{type:'product',name:'Photo-booth',total:249}])]),legacy_source:'studio_ninja'},expected:['Parent albums','Photo-booth']},
 {name:'separate imported album invoice',record:{...record([invoice('i1',[pkg]),invoice('i2',[],{number:'WBM02002',description:'Album add-on',total:75,paid:75})]),legacy_source:'studio_ninja'},expected:['Album add-on']},
 {name:'unitemised package does not imply selected extras',record:{...record([invoice('i1',[],{description:'Gold Package including album and photobooth'})]),legacy_source:'studio_ninja'},expected:[]},
 {name:'accepted linked quote fallback',record:record([invoice('i1',[])]),quote:{status:'accepted',invoice_id:'i1',line_items:[pkg,booth,album]},expected:[booth.name,album.name]},
 {name:'do not duplicate quote',record:record([invoice('i1',[pkg,booth,album])]),quote:{status:'accepted',invoice_id:'i1',line_items:[pkg,booth,album]},expected:[booth.name,album.name]},
 {name:'invoice snapshot wins over stale quote',record:record([invoice('i1',[pkg])]),quote:{status:'accepted',invoice_id:'i1',line_items:[pkg,booth,album]},expected:[]},
 {name:'unaccepted quote is not a selection',record:record([invoice('i1',[])]),quote:{status:'sent',invoice_id:'i1',line_items:[pkg,booth]},expected:[]},
 {name:'ignore quote belonging to another invoice',record:record([invoice('i1',[])]),quote:{status:'accepted',invoice_id:'other-booking-invoice',line_items:[pkg,booth]},expected:[]},
 {name:'paid retained but closed excluded',record:record([invoice('i1',[pkg,booth]),invoice('i2',[album],{status:'void'}),invoice('i3',[album],{status:'cancelled'})]),expected:[booth.name]},
 {name:'no closed quote fallback',record:record([invoice('i1',[],{status:'void'})]),quote:{status:'accepted',invoice_id:'i1',line_items:[pkg,booth]},expected:[]},
 {name:'separate invoice references',record:record([invoice('i1',[booth]),invoice('i2',[album],{number:'WBM02002'})]),expected:[booth.name,album.name]},
 {name:'no invoices is safe',record:record([]),expected:[]},
 {name:'invalid and removed rows',record:record([invoice('i1',[null,7,'Album',{}, {type:'addon',name:'Removed album',quantity:0,total:100},{type:'addon',name:'Album voucher',is_discount:true,total:100}, {type:'addon',name:'Extra album',quantity:1,total:'not recorded'}])]),expected:['Extra album']},
 {name:'escaped names',record:record([invoice('i1',[pkg,{type:'addon',name:'Album <img src=x onerror=alert(1)>',total:120}])]),expected:['Album <img src=x onerror=alert(1)>']},
];

(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.WBM_TEST_CHROME||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage();let requests=0;
  await page.route('**/*',r=>{requests++;return r.abort()});
  await page.setContent('<!doctype html><html data-wbm-theme="light"><head></head><body><main class="payments-test-shell"><h1>Emma &amp; James · Payments</h1><div id="content"></div></main></body></html>');
  for(const name of ['app.css','v82.css','v834.css','v848.css','v866.css','v866-dark.css','payment-extras.css'])await page.addStyleTag({content:fs.readFileSync(path.join(root,'app/static',name),'utf8')});
  await page.addStyleTag({content:'.payments-test-shell{max-width:1040px;margin:24px auto;padding:0 16px}.payments-test-shell>h1{font-size:23px;margin:0 0 20px}'});
  await page.addScriptTag({content:fs.readFileSync(path.join(root,'app/static/app.js'),'utf8').replace(/\binit\(\);\s*$/,'')});
  for(const name of ['v82.js','v834.js','v848.js'])await page.addScriptTag({content:fs.readFileSync(path.join(root,'app/static',name),'utf8')});
  await page.evaluate(()=>{
   window.baselineFinance=renderFinance;window.actions=[];
   api=async()=>{throw Error('Unexpected API call')};
   newInvoice=r=>window.actions.push(['new',r.id]);
   showPdfPreview=(...args)=>window.actions.push(['preview',...args]);
   recordPayment=(...args)=>window.actions.push(['payment',args[1],args[2]]);
  });
  await page.addScriptTag({content:fs.readFileSync(path.join(root,'app/static/payment-extras.js'),'utf8')});
  for(const fixture of cases){
   const result=await page.evaluate(({record,quote})=>{
    const body=document.querySelector('#content');state.currentPortal={quote};
    window.baselineFinance(record,body);
    const oldCards=body.querySelector('.invoice-cards').innerHTML;
    const before=JSON.stringify(record),quoteBefore=JSON.stringify(quote);
    renderFinance(record,body);
    const summary=body.querySelector('.payment-extras-summary');
    return {names:window.WBMPaymentExtras.items(record,quote).map(x=>x.name),
      unchanged:before===JSON.stringify(record)&&quoteBefore===JSON.stringify(quote),
      sameInvoiceHtml:oldCards===body.querySelector('.invoice-cards').innerHTML,
      count:body.querySelectorAll('.payment-extras-summary').length,
      position:body.querySelector('.section-actions').nextElementSibling===summary,
      outside:!summary.closest('.invoice-card'),text:summary.innerText};
   },fixture);
   assert.deepEqual(result.names,fixture.expected,fixture.name);
   assert(result.unchanged&&result.sameInvoiceHtml,fixture.name+': invoices and quote must stay unchanged');
   assert(result.position&&result.outside&&result.count===1,fixture.name+': correct placement');
   assert.equal(await page.locator('.payment-extras-summary img').count(),0);
   if(fixture.name==='later extras and discounts'){assert(result.text.includes('2 × Parent albums'));assert(result.text.includes('Added later'));assert(result.text.includes('No extra charge'));}
   if(fixture.name==='invalid and removed rows')assert(result.text.includes('Price not recorded'));
   if(fixture.name==='separate invoice references')assert(result.text.includes('WBM02001')&&result.text.includes('WBM02002'));
   if(fixture.name==='generic imported service lines')assert(result.text.includes('2 × Parent albums')&&result.text.includes('£150.00'));
  }
  await page.evaluate(fixture=>{state.currentPortal={};renderFinance(fixture,document.querySelector('#content'));},record([invoice('i1',[pkg,booth,album],{status:'part_paid',paid:100,balance:1168})]));
  await page.locator('[data-preview-invoice="i1"]').click();
  await page.locator('[data-payment-invoice="i1"]').click();
  await page.locator('#new-invoice').click();
  const actions=await page.evaluate(()=>window.actions);
  assert.deepEqual(actions.map(x=>x[0]),['preview','payment','new']);
  assert.deepEqual(actions[1],['payment','i1',1168]);
  for(const mode of ['light','dark'])for(const width of [320,390,768,1440]){
   await page.setViewportSize({width,height:1000});
   await page.evaluate(mode=>document.documentElement.dataset.wbmTheme=mode,mode);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,mode+' '+width);
   assert.equal(await page.locator('.payment-extras-summary li').count(),2);
   const metric=await page.locator('.payment-extras-summary li strong').first().evaluate(el=>({font:parseFloat(getComputedStyle(el).fontSize),width:el.getBoundingClientRect().width}));
   assert(metric.font>=16&&metric.width>0);
   if(process.env.WBM_EXTRAS_SCREENSHOTS&&[390,1440].includes(width))await page.screenshot({path:path.join(process.env.WBM_EXTRAS_SCREENSHOTS,`payment-extras-${mode}-${width}.png`),fullPage:true});
  }
  const long=record([invoice('i1',[{type:'addon',name:'Extra '+ 'A'.repeat(240),quantity:2,total:100}])]);
  await page.setViewportSize({width:320,height:900});await page.evaluate(r=>renderFinance(r,document.querySelector('#content')),long);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Long extra names must wrap');
  assert.equal(requests,0);
  console.log('PASS: 18 invoice/quote/import scenarios; invoice HTML, saved data and existing controls unchanged; no duplicate extras; correct placement; escaped and long names; readable 320/390/768/1440px layouts in light/dark themes. No API calls, writes or emails.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
