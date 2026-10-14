const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const fs=require('fs'),assert=require('node:assert/strict'),path=require('path');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:'/tmp/wbm-browser/chrome-linux/headless_shell'});
const page=await browser.newPage();let submissions=[];const errors=[];page.on('pageerror',e=>errors.push(e.message));
const app='https://booking.weddingsbymark.uk',site='https://perfectweddingsbymark.uk';
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'v869-enquiry-fixture.json')));fixture.fields=fixture.fields.filter(f=>f.enabled);
await page.route('**/*',async route=>{
 const u=new URL(route.request().url());
 if(u.origin===site)return route.fulfill({contentType:'text/html',body:`<meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0}.wbm-enquiry{padding:56px 20px}.wbm-form-wrap{padding:10px}iframe{min-height:1100px}</style><div class="wbm-contact"><div class="wbm-enquiry"><div class="wbm-inner"><div class="wbm-form-wrap"><iframe id="wbm-enquiry-form" data-src="${app}/enquiry" style="height:1600px;width:100%"></iframe><script src="${app}/static/enquiry-embed.js"></script></div></div></div></div>`});
 if(u.origin!==app)return route.abort();
 if(u.pathname==='/api/public/enquiry-form')return route.fulfill({json:fixture});
 if(u.pathname==='/api/public/catalog')return route.fulfill({json:{packages:[{name:'Full day photography and highlight video with a deliberately long package label',price:899}]}});
 if(u.pathname==='/api/public/config')return route.fulfill({json:{google_maps_enabled:false}});
 if(u.pathname==='/api/public/enquiries'){submissions.push(route.request().postDataJSON());return route.fulfill({json:{ok:true}});}
 const f=path.join(process.cwd(),'app',u.pathname==='/enquiry'?'static/enquiry.html':u.pathname);
 if(fs.existsSync(f))return route.fulfill({path:f});return route.abort();
});
for(const width of [320,360,390,412,768,1280]){
 await page.setViewportSize({width,height:844});await page.goto(site+'/contact/');
 // Reproduce WordPress replacing src with data-src until AFTER embed script loads.
 await page.evaluate(()=>{const f=document.querySelector('iframe');f.src=f.dataset.src;});
 const f=page.frameLocator('iframe');await f.locator('#submit-button:not([disabled])').waitFor();await f.locator('#enquiry-venue-manual:visible').waitFor();await page.waitForTimeout(150);
 const metrics=await f.locator('html').evaluate(el=>({width:innerWidth,scroll:el.scrollWidth,height:innerHeight,content:document.querySelector('main').getBoundingClientRect().height,field:document.querySelector('[name=email]').getBoundingClientRect().width}));
 assert(metrics.scroll<=metrics.width+1,JSON.stringify({width,...metrics}));assert(metrics.height>=metrics.content,JSON.stringify(metrics));assert(metrics.height-metrics.content<5,JSON.stringify(metrics));
 if(width<=412)assert(metrics.field>=width-30,JSON.stringify(metrics));
 await f.locator('[name=message]').evaluate(el=>el.style.height='650px');await page.waitForTimeout(100);
 await f.locator('[name=message]').evaluate(el=>el.style.height='100px');await page.waitForTimeout(100);
 assert(await f.locator('main').evaluate(el=>Math.abs(innerHeight-el.getBoundingClientRect().height)<5));
 if(width===390){await f.locator('[name=email]').scrollIntoViewIfNeeded();await page.screenshot({path:'/tmp/v869-mobile.png'});}
}
await page.setViewportSize({width:390,height:844});await page.goto(app+'/enquiry');await page.locator('#submit-button:not([disabled])').waitFor();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
await page.goto(site+'/contact/');await page.evaluate(()=>{const f=document.querySelector('iframe');f.src=f.dataset.src});const f=page.frameLocator('iframe');await f.locator('#submit-button:not([disabled])').waitFor();
await f.locator('[name=primary_first_name]').fill('Example');await f.locator('[name=partner_first_name]').fill('Partner');await f.locator('[name=email]').fill('example@example.com');await f.locator('[name=event_date]').fill('2027-08-20');await f.locator('#enquiry-venue-manual').fill('Example Hall');
await f.locator('[name=heard_about_us]').selectOption({index:1});await f.locator('[name=privacy_agreed]').check();await f.locator('#submit-button').click();await f.locator('#success:visible').waitFor();await page.waitForTimeout(150);assert.equal(await f.locator('#success').evaluate(el=>getComputedStyle(el).position),'static');assert.equal(submissions.length,1);assert.equal(submissions[0].location,'Example Hall');assert(await page.locator('iframe').evaluate(el=>el.getBoundingClientRect().height<600));assert.deepEqual(errors,[]);
await browser.close();console.log('PASS: 6 viewport widths, lazy-src resize handshake, no horizontal overflow, field widths, grow/shrink, standalone, manual venue and intercepted submission/confirmation.');
})().catch(e=>{console.error(e);process.exit(1)});
