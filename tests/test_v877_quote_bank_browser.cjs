/* Real quote renderer, fixture data and intercepted requests only. */
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'../app/static');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.WBM_TEST_CHROME,args:['--no-sandbox']});
 try{
 const page=await browser.newPage();const errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
 const bank={account_name:'Example & Partner <Bank>',sort_code:'04-05-06',account_number:'00987654'};
 let accepted=false,missing=false;
 await page.route('**/*',async route=>{
  const req=route.request(),u=new URL(req.url());if(req.method()!=='GET'){writes.push(req.url());return route.abort()}
  if(u.pathname.startsWith('/api/'))return route.fulfill({json:{business:{name:'Weddings By Mark',brand:'wbm',email:'example@example.com'},record:{title:'Example & Partner',kind:'wedding',status:'quoted',event_date:'2027-06-19',client:{first_name:'Example'},payment_reference:'EXAMPLE190627'},catalog:{packages:[{id:'pkg',code:'gold',name:'Example package',price:899,deposit_amount:150}],addons:[]},submissions:[],documents:[],invoices:accepted?[{id:'invoice',number:'WBM-EXAMPLE'}]:[],quote:accepted?{invoice_id:'invoice',invoice_number:'WBM-EXAMPLE',accepted_at:'2026-10-27',line_items:[{name:'Example package',total:899,type:'package'}],total:899,deposit_amount:150}:null,quote_bank_details:missing?{}:bank}});
  if(u.pathname.startsWith('/client/')||u.pathname.startsWith('/quote-preview/')){
   const file=u.pathname.startsWith('/quote-preview/')?'quote-preview.html':'client.html';
   let html=fs.readFileSync(path.join(root,file),'utf8').replace(/<script src="\/static\/client-v[^>]+><\/script>/g,'');
   return route.fulfill({contentType:'text/html',body:html});
  }
  const file=path.join(root,path.basename(u.pathname));if(/\.(css|js)$/.test(file)&&fs.existsSync(file))return route.fulfill({contentType:file.endsWith('.js')?'application/javascript':'text/css',body:fs.readFileSync(file)});
  return route.abort();
 });
 for(const preview of [false,true])for(const isAccepted of [false,true])for(const width of [320,390,768,1280]){
  accepted=isAccepted;missing=false;
  await page.setViewportSize({width,height:900});await page.emulateMedia({colorScheme:width===390?'dark':'light'});
  await page.goto('https://quote.test/'+(preview?'quote-preview':'client')+'/fixture?tab=quote');
  const block=page.locator('.quote-payment-reference .quote-bank-details');await block.waitFor();
  assert.equal(await block.locator('div').count(),3);assert((await block.innerText()).includes(bank.account_name));assert((await block.innerText()).includes(bank.account_number));assert.equal(await block.locator('img').count(),0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`overflow ${preview}/${accepted}/${width}`);
  if(!accepted){await page.locator('label.package-card').click();assert((await page.locator('#quote-total').innerText()).includes('899'));assert.equal(await page.locator('#quote-form button[type="submit"]').isDisabled(),preview)}
  assert((await page.locator('.quote-payment-reference').innerText()).indexOf('EXAMPLE190627')<(await page.locator('.quote-payment-reference').innerText()).indexOf(bank.account_name));
 }
 missing=true;accepted=false;await page.goto('https://quote.test/client/fixture?tab=quote');await page.locator('.quote-bank-help').waitFor();assert.equal(await page.locator('.quote-bank-details').count(),0);
 assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
 console.log('PASS: chosen account below reference in pending/accepted live quotes and previews, leading zeros, escaped names, missing-details guidance, package controls, no writes, 320/390/768/1280px layouts.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
