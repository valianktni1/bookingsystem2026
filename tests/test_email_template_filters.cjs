/* Exercise the actual communications renderer with read-only API fixtures. */
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const runtime=process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES||'C:/Users/Mark/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const {chromium}=require(path.join(runtime,'playwright'));
const root=path.resolve(__dirname,'..');
function contrast(a,b){const luminance=s=>{const rgb=s.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4)});return rgb[0]*0.2126+rgb[1]*0.7152+rgb[2]*0.0722};const x=luminance(a),y=luminance(b);return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05)}
const data={smtp_by_brand:{wbm:{configured:true,username:'mark@example.com'},ivory:{configured:true,username:'studio@example.com'}},smtp_configured:true,reminders_enabled:true,
 templates:[
 {id:'quote',brand:'wbm',display_name:'Initial wedding quote',subject:'Your wedding quote',template_key:'quote',is_active:true,usage_kind:'action',usage_label:'Sent when you send a quote'},
 {id:'review',brand:'wbm',display_name:'14-day wedding review & awards request',subject:'How’s married life treating you both?',template_key:'post_wedding_review',is_active:true,usage_kind:'automatic',usage_label:'14 days after the wedding'},
 {id:'checkin',brand:'wbm',display_name:'Wedding check-in',subject:'Your wedding plans',template_key:'check_in_120',is_active:true,usage_kind:'automatic'},
 {id:'manual',brand:'wbm',display_name:'Personal follow-up',subject:'A quick hello',template_key:'personal_note',is_active:true,usage_kind:'manual'},
 {id:'ivory',brand:'ivory',display_name:'Project update',subject:'Your website',template_key:'update',is_active:true,usage_kind:'manual'},
 {id:'inactive',brand:'wbm',display_name:'Old balance reminder',subject:'Balance update',template_key:'balance_due_10',is_active:false,usage_kind:'inactive'},
 {id:'inactive-auto',brand:'wbm',display_name:'Paused check-in template',subject:'Hidden automatic',template_key:'old_checkin',is_active:false,usage_kind:'automatic'},
 {id:'fallback',brand:'wbm',display_name:'Custom "hello" <img src=x onerror=alert(1)>',subject:'A safe custom template',template_key:'custom_note',is_active:true}],
 contracts:[{id:'agreement',brand:'wbm',title:'Weddings By Mark agreement',version:'Current version'}]};

(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.WBM_TEST_CHROME||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage();await page.route('**/*',r=>r.abort());
  await page.setContent('<!doctype html><html><head></head><body><main id="content"></main></body></html>');
  const index=fs.readFileSync(path.join(root,'app/static/index.html'),'utf8');
  for(const match of index.matchAll(/href="\/static\/([^"?]+\.css)(?:\?[^" ]*)?"/g)){
   await page.addStyleTag({content:fs.readFileSync(path.join(root,'app/static',match[1]),'utf8')});
  }
  await page.addScriptTag({content:fs.readFileSync(path.join(root,'app/static/email-template-filters.js'),'utf8')});
  const app=fs.readFileSync(path.join(root,'app/static/app.js'),'utf8').replace(/\binit\(\);\s*$/,'');
  await page.addScriptTag({content:app});
  await page.evaluate(async fixture=>{
   window.fixture=fixture;window.apiCalls=[];window.actions=[];
   api=async(url,options={})=>{
    window.apiCalls.push({url,method:options.method||'GET'});
    if(!url.startsWith('/api/communications/templates'))throw Error('Unexpected request: '+url);
    const brand=new URL(url,'https://example.com').searchParams.get('brand');
    return {...window.fixture,templates:window.fixture.templates.filter(t=>!brand||t.brand===brand)};
   };
   previewEmailTemplate=t=>window.actions.push(['preview',t.id]);
   editEmailTemplate=t=>window.actions.push(['edit',t.id]);
   deleteEmailTemplate=t=>window.actions.push(['delete',t.id]);
   state.view='communications';state.brand='all';await renderCommunicationsV2();
  },data);
  const rows=()=>page.locator('#email-template-list [data-email-template-kind]:visible');
  const filter=kind=>page.locator(`[data-email-template-filter="${kind}"]`);
  assert.equal(await rows().count(),8);
  assert.equal(await page.locator('img').count(),0,'Template names remain escaped');
  for(const [kind,count] of [['automatic',2],['manual',3],['action',1],['inactive',2],['all',8]]){
   await filter(kind).click();assert.equal(await rows().count(),count,kind);
   assert.equal(await filter(kind).getAttribute('aria-pressed'),'true');
   assert.equal(await page.locator('[data-contract="agreement"]').isVisible(),true);
  }
  await filter('automatic').click();await page.locator('#email-template-search').fill('AWARDS');
  assert.equal(await rows().count(),1);
  await page.locator('[data-preview-template="review"]').click();
  await page.locator('[data-edit-template="review"]').click();
  assert.deepEqual(await page.evaluate(()=>window.actions),[['preview','review'],['edit','review']]);
  await page.locator('#email-template-search').fill('nothing-matches');
  assert.equal(await rows().count(),0);assert.equal(await page.locator('.email-template-filter-empty').isVisible(),true);
  await page.locator('[data-email-template-clear]').click();assert.equal(await rows().count(),8);
  await filter('manual').focus();await page.keyboard.press('Space');assert.equal(await rows().count(),3);
  assert.equal(await filter('manual').evaluate(el=>getComputedStyle(el).outlineWidth),'3px');
  await page.locator('#email-template-search').fill('personal');
  await page.evaluate(()=>renderCommunicationsV2());
  assert.equal(await page.locator('#email-template-search').inputValue(),'personal');
  assert.equal(await rows().count(),1,'Selection survives a communications refresh');
  await page.locator('[data-email-template-clear]').click();await filter('automatic').click();
  await page.evaluate(async()=>{state.brand='ivory';await renderCommunicationsV2()});
  assert.equal(await rows().count(),0);assert.equal(await page.locator('.email-template-filter-empty').isVisible(),true);
  await page.locator('[data-email-template-clear]').click();assert.equal(await rows().count(),1,'Brand filter still applies');
  await page.evaluate(async()=>{state.brand='all';await renderCommunicationsV2()});
  for(const theme of ['light','dark'])for(const width of [320,390,768,1440]){
   await page.setViewportSize({width,height:1000});
   await page.evaluate(theme=>document.documentElement.dataset.wbmTheme=theme,theme);
   await filter('automatic').click();
   const metrics=await filter('automatic').evaluate(el=>({height:el.getBoundingClientRect().height,font:parseFloat(getComputedStyle(el).fontSize),bg:getComputedStyle(el).backgroundColor,ink:getComputedStyle(el).color,opacity:getComputedStyle(el).opacity}));
   assert(metrics.height>=48);assert(metrics.font>=16);
   assert(contrast(metrics.bg,metrics.ink)>=4.5,'Readable selected-button contrast: '+theme);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No overflow: '+theme+' '+width);
   if(process.env.WBM_FILTER_SCREENSHOTS && [390,1440].includes(width))await page.screenshot({path:path.join(process.env.WBM_FILTER_SCREENSHOTS,`email-template-filters-${theme}-${width}.png`),fullPage:true});
  }
  assert((await page.evaluate(()=>window.apiCalls)).every(r=>r.method==='GET'),'Filtering must never write or send emails');
  console.log('PASS: category counts, current usage labels, search, inactive and custom templates, empty/reset states, preserved selection, brand filtering, preview/edit actions, keyboard focus, 48px controls and light/dark layouts at 320/390/768/1440px. No writes or emails.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
