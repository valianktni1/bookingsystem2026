/* Production enquiry page + embed script, intercepted API only; no live writes. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'../app/static');
const config={heading:'Wedding enquiry',introduction:'Example studio enquiry',success_heading:'Thank you for your enquiry!',success_message:'Your enquiry has arrived safely. '+('LongConfirmationWord'.repeat(20)),submit_label:'Submit enquiry',payment_options:[],fields:[
 {key:'primary_first_name',label:'Your first name',field_type:'text',required:true},
 {key:'email',label:'Email address',field_type:'email',required:true},
 {key:'location',label:'Venue',field_type:'text',required:true},
 {key:'privacy_agreed',label:'I agree to the privacy notice',field_type:'checkbox',required:true}
]};
(async()=>{const browser=await chromium.launch({executablePath:process.env.WBM_TEST_CHROME,headless:true,args:['--no-sandbox']});try{
for(const embedded of [false,true])for(const [width,height] of [[320,740],[390,844],[430,932],[844,390],[1280,900]]){
 const page=await browser.newPage({viewport:{width,height}}),errors=[];let writes=0,failed=true;
 page.on('pageerror',e=>errors.push(String(e)));
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.pathname==='/host')return route.fulfill({contentType:'text/html',body:'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0}iframe{width:100%;border:0}</style><iframe id="wbm-enquiry-form" src="https://booking-fixture.invalid/enquiry" height="2000"></iframe><script data-iframe-id="wbm-enquiry-form" src="https://booking-fixture.invalid/static/enquiry-embed.js"></script>'});
  if(u.pathname==='/enquiry')return route.fulfill({path:path.join(root,'enquiry.html'),contentType:'text/html'});
  if(u.pathname==='/api/public/enquiry-form')return route.fulfill({json:config});
  if(u.pathname==='/api/public/enquiries'){
   writes++;await new Promise(resolve=>setTimeout(resolve,100));
   return route.fulfill(failed?{status:422,json:{detail:'Example validation failure'}}:{status:201,json:{ok:true}});
  }
  if(u.pathname.startsWith('/static/')&&fs.existsSync(path.join(root,u.pathname.slice(8))))return route.fulfill({path:path.join(root,u.pathname.slice(8))});
  return route.abort();
 });
 await page.goto(embedded?'https://perfectweddingsbymark.uk/host':'https://booking-fixture.invalid/enquiry');
 const target=embedded?page.frameLocator('iframe'):page;
 await target.locator('#submit-button').waitFor({state:'visible'});
 await target.locator('[name=primary_first_name]').fill('Example');await target.locator('[name=email]').fill('example@example.com');await target.locator('[name=location]').fill('Example venue');await target.locator('[name=privacy_agreed]').check();
 await target.locator('#submit-button').click();
 await target.locator('#form-error').filter({hasText:'Example validation failure'}).waitFor();
 assert(await target.locator('#enquiry-card').isVisible());assert(!(await target.locator('#success').isVisible()));
 assert.equal(await target.locator('[name=primary_first_name]').inputValue(),'Example');
 failed=false;await target.locator('#submit-button').click();
 await target.locator('#success').waitFor({state:'visible'});
 const bounds=await target.locator('#success').evaluate(el=>({left:el.getBoundingClientRect().left,right:el.getBoundingClientRect().right,width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,position:getComputedStyle(el).position}));
 assert(bounds.left>=-1&&bounds.right<=bounds.width+1,JSON.stringify({embedded,width,bounds}));assert(!bounds.overflow,JSON.stringify({embedded,width,bounds}));assert.equal(bounds.position,'static');
 if(embedded){await page.waitForTimeout(150);const frame=await page.locator('iframe').boundingBox();assert(frame.width<=width+1);assert(frame.height<1000,'Embed should shrink after success');}
 if(width===390&&embedded)await page.screenshot({path:'/tmp/wbm-enquiry-success-mobile.png',fullPage:true});
 assert.equal(writes,2);assert.deepEqual(errors,[]);await page.close();
}
console.log('Mobile confirmation passed: standalone + embed at 320/390/430/844/1280px, long text, failure retains answers, success only after response.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
