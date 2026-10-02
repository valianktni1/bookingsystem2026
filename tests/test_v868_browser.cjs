/* Disposable local app only. Email delivery is intercepted, never sent. */
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const base=process.env.WBM_TEST_URL||'http://127.0.0.1:8768';
 assert.match(base,/^http:\/\/(127\.0\.0\.1|localhost):/);
 const browser=await chromium.launch({headless:true,executablePath:'/tmp/wbm-browser/chrome-linux/headless_shell'});
 const p=await browser.newPage({viewport:{width:390,height:844},colorScheme:'dark'});
 const errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(base);await p.locator('#login-email').fill('mark@example.com');await p.locator('#login-password').fill('SecureTestPassword!123');await p.locator('#login-form button').click();await p.locator('#app:not(.hidden)').waitFor();
 const res=await p.request.post(base+'/api/bookings',{data:{brand:'wbm',kind:'wedding',status:'enquiry',title:'Attachment test',client:{first_name:'Alex',last_name:'Example',email:'alex@example.com'},event_date:'2027-06-12'}});assert(res.ok());const booking=await res.json();
 await p.evaluate(id=>openDrawer(id),booking.id);await p.locator('#record-email-client-top').click();await p.locator('#client-email-files').waitFor();
 await p.locator('#client-email-mode').selectOption('manual');await p.locator('#client-email-subject').fill('Information attached');await p.locator('#client-email-body').fill('Hi Alex, see attached.');
 const pdf={name:'Wedding-information.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.7\nexample')};
 const jpg={name:'Venue-photo.jpeg',mimeType:'image/jpeg',buffer:Buffer.from([255,216,255,1])};
 await p.locator('#client-email-files').setInputFiles([pdf,jpg]);assert.equal(await p.locator('#client-email-file-list li').count(),2);
 await p.locator('[data-remove-file="1"]').click();assert.equal(await p.locator('#client-email-file-list li').count(),1);
 await p.locator('#client-email-files').setInputFiles({name:'bad.exe',mimeType:'application/octet-stream',buffer:Buffer.from('bad')});assert.match(await p.locator('#client-email-file-error').innerText(),/Choose a PDF/);assert.equal(await p.locator('#client-email-file-list li').count(),1);
 await p.locator('#client-email-files').setInputFiles(jpg);
 await p.locator('#client-email-files').scrollIntoViewIfNeeded();assert.equal(await p.evaluate(()=>document.querySelector('#modal-content').scrollWidth>document.querySelector('#modal-content').clientWidth+1),false);
 await p.screenshot({path:'/tmp/v868-mobile-dark.png'});
 await p.evaluate(()=>{const control=document.querySelector('#drawer [data-wbm-appearance]');control.value='light';control.dispatchEvent(new Event('change',{bubbles:true}));});await p.screenshot({path:'/tmp/v868-mobile-light.png'});
 let attempts=0;await p.route('**/api/bookings/*/email-centre/send',async route=>{
   attempts++;const data=route.request().postDataJSON();assert.equal(data.attachments.length,2);assert.equal(data.attachments[0].content_base64,pdf.buffer.toString('base64'));assert.equal(data.subject,'Information attached');
   await route.fulfill({status:attempts===1?503:200,contentType:'application/json',body:JSON.stringify(attempts===1?{detail:'Test delivery failure'}:{recipient:'alex@example.com'})});
 });
 await p.locator('#dynamic-form button[type=submit]').click();await p.getByText('Test delivery failure',{exact:true}).waitFor();assert.equal(await p.locator('#client-email-file-list li').count(),2);assert.equal(await p.locator('#client-email-subject').inputValue(),'Information attached');
 await p.setViewportSize({width:1280,height:900});await p.locator('#client-email-files').scrollIntoViewIfNeeded();await p.screenshot({path:'/tmp/v868-desktop-light.png'});
 await p.locator('#dynamic-form button[type=submit]').click();await p.locator('#modal').waitFor({state:'hidden'});assert.equal(attempts,2);assert.deepEqual(errors,[]);
 await browser.close();console.log('PASS mobile/desktop attachment add/remove, invalid file, dark/light, failure preserves draft/files, successful send payload. No real email sent.');
})().catch(error=>{console.error(error);process.exit(1)});
