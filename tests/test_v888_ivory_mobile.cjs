const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'../app/static'),origin='https://example.test';
const starter={title:'Website design and agreed additions',customer:'The Kitchen Factory Liverpool',email:'',address:'',intro:'Website design and build.',terms:'Balance due before launch. No VAT charged.',opening_paid:'599.50',opening_paid_date:'2026-10-19',lines:[{name:'Original website design and build',description:'WordPress website with mobile layout.',amount:'1199.00',kind:'one_off',selected:true},{name:'Additional supplier collection content',description:'Agreed content.',amount:'150.00',kind:'one_off',selected:true},{name:'Approved trade accounts and pricing',description:'Trade application and approval.',amount:'300.00',kind:'one_off',selected:true}]};
(async()=>{const browser=await chromium.launch({executablePath:process.env.WBM_TEST_CHROME||'/tmp/chromium',headless:true,args:['--no-sandbox']});
try{for(const width of [320,390,1280])for(const dark of [false,true]){
  const page=await browser.newPage({viewport:{width,height:850}});let rows=[],posts=[],errors=[],templates=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{const url=new URL(route.request().url()),p=url.pathname,method=route.request().method();
    if(url.origin!==origin)return route.abort();
    if(p==='/test')return route.fulfill({contentType:'text/html',body:`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0;font:16px system-ui;padding:12px;${dark?'--wbm-surface:#222e2a;--ink:#edf5f1;--bg:#17211d;--line:#485e51;--wbm-action:#9edbc7;--wbm-action-text:#143d30;background:#17211d;color:#edf5f1':''}}</style><link rel="stylesheet" href="/static/ivory-quotes.css"><div id="page-eyebrow"></div><h1 id="page-title"></h1><p id="page-subtitle"></p><div id="content"></div><div id="toast"></div><script>const state={view:'ivoryquotes'};let render=()=>{};const toast=t=>document.querySelector('#toast').textContent=t;const api=async(u,o)=>{const r=await fetch(u,o);return r.json()};const emailInvoice=()=>{throw Error('Mail must not be sent')};const openDrawer=()=>{};</script><script src="/static/ivory-quotes.js"></script><script>render();</script>`});
    if(p==='/api/ivory-quotes/projects')return route.fulfill({json:[]});
    if(p==='/api/ivory-quotes/starter')return route.fulfill({json:starter});
    if(p==='/api/ivory-quotes/templates'){if(method==='PUT')templates=route.request().postDataJSON().items;return route.fulfill({json:{items:templates}});}
    if(p==='/api/ivory-quotes'){
      if(method==='POST'){const data=route.request().postDataJSON();posts.push(data);rows.push({id:'test-id',booking_id:'project-test',reference:'IDQ-EXAMPLE-R1',revision:1,status:'draft',details:data.details,total:1649,monthly:0,invoice:null});return route.fulfill({status:201,json:rows[0]});}
      return route.fulfill({json:rows});}
    if(p==='/api/ivory-quotes/test-id/accept'){
      posts.push(route.request().postDataJSON());rows[0].status='accepted';rows[0].invoice={id:'invoice-test',number:'WBM02001',total:1649,paid:599.50,balance:1049.50};return route.fulfill({json:rows[0]});}
    if(p.startsWith('/ivory-quote/'))return route.fulfill({path:path.join(root,'ivory-quote.html')});
    if(p==='/api/public/ivory-quotes/test'){return route.fulfill({json:{...rows[0],status:rows[0].status==='accepted'?'accepted':'shared'}});}
    if(p==='/api/public/ivory-quotes/test/accept'){posts.push(route.request().postDataJSON());rows[0].status='accepted';return route.fulfill({json:{ok:true,number:'WBM02001'}});}
    if(p.startsWith('/static/')&&fs.existsSync(path.join(root,p.slice(8))))return route.fulfill({path:path.join(root,p.slice(8))});
    return route.abort();});
  await page.goto(origin+'/test');await page.getByRole('button',{name:'Prepare Andy’s agreed invoice'}).click();
  const d=page.getByRole('dialog');await d.getByLabel('Customer email').fill('andy@example.com');
  assert.equal(await d.getByLabel('Date payment received').inputValue(),'2026-10-19');
  assert.match(await d.locator('[data-total]').innerText(),/£1,049.50/);
  const overflow=()=>page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  assert(!(await overflow()),'page overflow '+width);
  assert(!(await d.evaluate(el=>el.scrollWidth>el.clientWidth+1)),'dialog overflow '+width);
  if(dark){const style=await d.evaluate(el=>({background:getComputedStyle(el).backgroundColor,color:getComputedStyle(el).color}));assert.equal(style.background,'rgb(34, 46, 42)');assert.equal(style.color,'rgb(237, 245, 241)');}
  await d.getByRole('button',{name:'Save draft',exact:true}).click();await d.waitFor({state:'hidden'});
  assert.equal(posts[0].details.opening_paid,'599.50');assert.equal(posts[0].details.lines.length,3);
  await page.getByRole('button',{name:'Record agreement & create invoice'}).click();
  const agreement=page.getByRole('dialog');await agreement.getByLabel('Who agreed?').fill('Andy');await agreement.getByLabel('What was agreed and when?').fill('Changes agreed by phone.');await agreement.getByRole('checkbox').check();await agreement.getByRole('button',{name:'Create agreed invoice'}).click();await agreement.waitFor({state:'hidden'});
  assert.match(await page.locator('[data-offers]').innerText(),/WBM02001/);assert.match(await page.locator('[data-offers]').innerText(),/£1,049.50/);
  await page.getByRole('button',{name:'Quote additional services'}).click();assert.equal(await page.getByRole('dialog').getByLabel('Payment already received (£)').inputValue(),'0');await page.getByRole('button',{name:'Cancel',exact:true}).click();
  rows[0].status='shared';await page.goto(origin+'/ivory-quote/test');await page.getByRole('heading',{name:starter.title}).waitFor();assert(!(await overflow()),'client overflow '+width);await page.getByLabel('Your name').fill('Andy');await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Accept quote & create invoice'}).click();await page.getByRole('heading',{name:'Quote accepted',exact:true}).waitFor();assert(!(await overflow()));assert.deepEqual(errors,[]);
  await page.screenshot({path:`/tmp/ivory-v888-${width}-${dark?'dark':'light'}.png`,fullPage:true});await page.close();
}console.log('Ivory admin and client quote flows verified at 320, 390 and 1280px in light and dark themes.');}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
