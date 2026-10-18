/* Render-only email checks. No app, mailbox or external requests are allowed. */
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const fs=require('fs'),assert=require('assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.WBM_TEST_CHROME||'/tmp/wbm-browser/chrome-linux/headless_shell',args:['--no-sandbox']});
 try{
 const p=await browser.newPage();let network=0;
 await p.route('**/*',r=>{network++;return r.abort();});
 const markup=fs.readFileSync('/tmp/wbm-v873-email.html','utf8');
 for(const mode of ['light','dark'])for(const width of [320,390,412,600,1280]){
  await p.setViewportSize({width,height:900});await p.emulateMedia({colorScheme:mode});await p.setContent(markup);
  const metrics=await p.evaluate(()=>{
   const cell=document.querySelector('.wbm-email-message'),card=document.querySelector('.wbm-email-card');
   const c=getComputedStyle(cell);return {scroll:document.documentElement.scrollWidth,viewport:innerWidth,card:card.getBoundingClientRect().width,pad:Number.parseFloat(c.paddingLeft)+Number.parseFloat(c.paddingRight),bg:c.backgroundColor,ink:c.color};
  });
  assert(metrics.scroll<=width,'Horizontal overflow at '+width);
  if(width<=640){assert(metrics.card>=width-1,'Card must fill available phone width');assert.equal(metrics.pad,32,'Readable 16px side padding');}
  else assert(metrics.card<=641,'Keep desktop reading width');
  assert.equal(metrics.bg,mode==='light'?'rgb(255, 255, 255)':'rgb(34, 46, 42)');
  assert.equal(metrics.ink,mode==='light'?'rgb(45, 43, 40)':'rgb(237, 245, 241)');
  assert.equal(await p.locator('.wbm-email-header img').evaluate(i=>i.complete&&i.naturalWidth>0),true);
  assert.equal(await p.locator('.wbm-email-awards img').evaluate(i=>i.complete&&i.naturalWidth>0),true);
  if(width===390)await p.screenshot({path:'/tmp/wbm-v873-'+mode+'.png',fullPage:true});
 }
 // A reply may strip styles/head and add its own indentation. Fill the width
 // it provides without depending on media queries or trying to override it.
 await p.setViewportSize({width:320,height:900});await p.emulateMedia({colorScheme:'light'});await p.setContent(markup);
 const inner=await p.locator('body').innerHTML();
 await p.setContent('<html><body style="margin:0"><blockquote style="margin:0 24px">'+inner+'</blockquote></body></html>');
 let m=await p.locator('.wbm-email-card').boundingBox();assert(m.width>=270&&m.width<=272);
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 // Long manual text/URLs must wrap rather than make the mail app shrink it.
 await p.locator('.wbm-email-message').evaluate(el=>{el.textContent='X'.repeat(300);});
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.equal(network,0,'No mail, tracking or app requests');
 console.log('PASS: 320/390/412/600/1280px, light/dark, decoded embedded images, full available phone width, constrained desktop width, stripped quoted-reply layout and long content. No network requests.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
