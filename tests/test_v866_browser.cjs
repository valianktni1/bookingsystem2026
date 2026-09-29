/* Local-only browser regression. Run with a disposable server at WBM_TEST_URL. */
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const fs=require('fs');
(async()=>{
 const base=process.env.WBM_TEST_URL||'http://127.0.0.1:8766';if(!/^http:\/\/(127\.0\.0\.1|localhost):/.test(base))throw Error('Local test server required');
 const b=await chromium.launch({headless:true,executablePath:process.env.WBM_TEST_CHROME||'/tmp/wbm-browser/chrome-linux/headless_shell'});
 const p=await b.newPage({viewport:{width:390,height:844},colorScheme:'dark'});const errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(base+'/enquiries');await p.locator('#login-email').fill('mark@example.com');await p.locator('#login-password').fill('SecureTestPassword!123');await p.locator('#login-form button').click();await p.locator('#app:not(.hidden)').waitFor();
 const req=p.request;
 async function api(url,data,method='post'){let res=await req[method](base+url,{data});if(!res.ok())throw Error(url+' '+await res.text());return res.json();}
 const r=await api('/api/bookings',{brand:'wbm',kind:'wedding',status:'enquiry',title:'Mobile workspace test',client:{first_name:'Sophie',last_name:'Example',email:'sophie@example.com',partner_name:'Jamie'},event_date:'2027-06-12',venue_or_project:'Test Hall'});
 const banks=await api('/api/quote-bank-accounts',undefined,'get');banks[1]={...banks[1],label:'New test bank',account_name:'Synthetic account',sort_code:'123456',account_number:'12345678'};await api('/api/quote-bank-accounts',{accounts:banks},'put');
 const catalog=await api('/api/catalog?brand=wbm',undefined,'get');const pkg=catalog.packages[0];
 const template=await api('/api/quote-templates',{name:'Browser template',package_ids:[pkg.id],optional_addon_ids:[],required_addons:[],discounts:[],bank_account_id:'alternate',subject:'Your wedding options',body:'Hi {client_first_name}, here are your options.'});
 await p.evaluate(id=>openDrawer(id),r.id);await p.locator('.v866-board').waitFor();await p.waitForTimeout(250);await p.screenshot({path:'/tmp/v866-mobile-dark.png',fullPage:true});
 if(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile page overflow');
 await p.locator('#drawer [data-wbm-appearance]').selectOption('light');await p.waitForTimeout(250);await p.screenshot({path:'/tmp/v866-mobile-light.png',fullPage:true});
 await p.locator('[data-v866-action=enquiry]').click();await p.locator('.v861-paper').waitFor();await p.locator('#close-modal').click();
 await p.locator('[data-v866-action=quote]').click();await p.locator('#v857-offer-choice').waitFor();await p.locator('#v857-offer-choice').selectOption(template.id);
 if(await p.locator('#offer-bank').inputValue()!=='alternate')throw Error('Template bank not selected');
 await p.waitForTimeout(250);await p.screenshot({path:'/tmp/v866-prepare-light.png',fullPage:true});
 await p.locator('#dynamic-form footer .primary').click();await p.locator('#quote-email-subject').waitFor();await p.locator('.v858-summary').waitFor();
 if(!(await p.locator('.v858-summary').innerText()).includes('New test bank'))throw Error('Bank missing from quote review');
 if(await p.locator('#quote-email-subject').inputValue()!=='Your wedding options')throw Error('Template email lost');
 await p.evaluate(()=>{document.querySelector('#drawer [data-wbm-appearance]').value='dark';document.querySelector('#drawer [data-wbm-appearance]').dispatchEvent(new Event('change',{bubbles:true}));});
 await p.waitForTimeout(250);await p.screenshot({path:'/tmp/v866-review-dark.png',fullPage:true});
 // Check the final UI send handler without delivering any message.
 let sent=false;await p.route('**/api/bookings/*/quote/send',async route=>{sent=true;const body=route.request().postDataJSON();if(body.subject!=='Your wedding options')throw Error('Wrong send payload');await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({url:base+'/client/test',email_sent:true})});});
 await p.locator('#dynamic-form footer .primary').click();await p.locator('#modal').waitFor({state:'hidden'});if(!sent)throw Error('Send handler not called');
 for(const tab of ['Overview','Journey','Emails','Payments','Files','Activity']){await p.locator('#drawer [data-tab='+tab+']').click();await p.waitForTimeout(250);if(await p.locator('.v844-section-error').count())throw Error('Section error '+tab);}
 await p.locator('#drawer [data-tab=Overview]').click();await p.setViewportSize({width:1280,height:900});await p.locator('#drawer').evaluate(el=>el.scrollTo(0,0));await p.waitForTimeout(250);await p.screenshot({path:'/tmp/v866-desktop-dark.png',fullPage:true});
 await p.reload();await p.locator('.v866-board').waitFor();if(await p.locator('html').getAttribute('data-wbm-theme')!=='dark')throw Error('Theme not remembered');
 await p.locator('#drawer [data-wbm-appearance]').selectOption('system');await p.emulateMedia({colorScheme:'light'});await p.waitForTimeout(100);if(await p.locator('html').getAttribute('data-wbm-theme')!=='light')throw Error('System theme not updated');
 await p.locator('#close-drawer').click();await p.locator('#drawer').waitFor({state:'hidden'});
 const fixture=JSON.parse(fs.readFileSync('/tmp/wbm-v865-fixture.json','utf8'));await p.evaluate(id=>openDrawer(id),fixture.booking);await p.locator('.v866-board').waitFor();await p.locator('[data-v866-action=timings]').first().click();await p.locator('.v821-answer-modal').waitFor();await p.locator('#close-modal').click();
 await p.evaluate(id=>openDrawer(id),r.id);await p.locator('.v866-board').waitFor();await p.locator('#drawer').evaluate(el=>el.scrollTo(0,0));await p.waitForTimeout(500);await p.screenshot({path:'/tmp/v866-desktop-final.png',fullPage:true});
 if(errors.length)throw Error(errors.join('\n'));console.log('PASS: native overview, direct enquiry/timings, saved template + bank + email, quote prepare/review/send handler (delivery intercepted), all six booking sections, theme persistence/system changes, reload/back, desktop/mobile.');await b.close();
})();
