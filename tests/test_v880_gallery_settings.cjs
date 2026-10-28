/* Isolated settings and gallery-link UI. Uses production styles; API is mocked. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'../app/static');
(async()=>{const browser=await chromium.launch({executablePath:process.env.WBM_TEST_CHROME,headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:390,height:900}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:'<html></html>'});const f=u.pathname.startsWith('/static/')?path.join(root,path.basename(u.pathname)):null;return f&&fs.existsSync(f)?route.fulfill({path:f}):route.abort()});
 await page.goto('https://booking-fixture.invalid/').catch(()=>{});
 const links=fs.readFileSync(path.join(root,'index.html'),'utf8').match(/<link[^>]+rel="stylesheet"[^>]*>/g).join('');
 await page.setContent(`<html><head>${links}</head><body><main id="content"></main><div id="modal" class="modal hidden"><div id="modal-content"><form id="dynamic-form"></form></div></div></body></html>`);
 await page.evaluate(()=>{
  window.writes=[];window.toasts=[];window.esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');window.attr=window.esc;
  window.renderSettings=async()=>{};window.renderOverview=(r,body)=>body.innerHTML='<div class="v866-right"></div>';window.WBMSetup={native:r=>!r.legacy_source};window.closeModal=()=>document.querySelector('#modal').classList.add('hidden');window.toast=s=>window.toasts.push(s);
  window.showModal=(title,html,save)=>{const modal=document.querySelector('#modal');modal.classList.remove('hidden');const form=document.querySelector('#dynamic-form');form.innerHTML='<div class="modal-head"><h2>Wedding galleries</h2></div><div class="form-grid">'+html+'</div><footer><button type="submit" class="primary">Save</button></footer>';form.onsubmit=e=>{e.preventDefault();save()}};
  window.api=async(url,options={})=>{if(options.method){window.writes.push({url,...options});return {ok:true}}if(url.endsWith('/settings'))return {enabled:false,key_saved:false,rules:{},items:[{key:'package:example',name:'Example full-day package',kind:'Package',active:true},{key:'addon:free-album',name:'Complimentary album',kind:'Adjustment',active:true}]};if(url.endsWith('/jobs'))return [];return {status:'created',result:{admin_url:'https://weddingsbymark.uk/admin/gallery/fixture',guest_url:'https://weddingsbymark.uk/s/johnnikkiguestuploads'}};};
 });
 await page.addScriptTag({path:path.join(root,'v880.js')});await page.evaluate(()=>renderSettings());await page.locator('#gallery-connection-open').click();
 assert.equal(await page.evaluate(()=>writes.length),0);await page.locator('[data-gallery-rule="package:example"] [data-rule-field=configured]').check();await page.locator('[data-gallery-rule="package:example"] [data-rule-field=photography]').check();await page.locator('[data-gallery-rule="package:example"] [data-rule-field=full_day]').check();await page.locator('[data-gallery-rule="addon:free-album"] [data-rule-field=album_mode]').selectOption('40');
 await page.locator('#gallery-key').fill('wbm_gallery_ISOLATED_FIXTURE_ONLY_NOT_A_REAL_KEY');await page.locator('#dynamic-form button[type=submit]').click();
 const writes=await page.evaluate(()=>writes);assert.equal(writes.length,1);const data=JSON.parse(writes[0].body);assert.equal(data.enabled,false);assert.equal(data.rules['addon:free-album'].album_mode,'40');assert.equal(data.rules['package:example'].full_day,true);
 for(const theme of ['light','dark'])for(const width of [320,390,768,1280]){await page.setViewportSize({width,height:900});await page.evaluate(theme=>document.documentElement.setAttribute('data-wbm-theme',theme),theme);await page.locator('#gallery-connection-open').click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);if(width===390)await page.screenshot({path:`/tmp/wbm-booking-gallery-settings-${theme}.png`});await page.evaluate(()=>closeModal())}
 assert.deepEqual(errors,[]);console.log('PASS booking gallery settings: exact mapping payload; explicit save; mobile/desktop and both themes; no implicit writes.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
