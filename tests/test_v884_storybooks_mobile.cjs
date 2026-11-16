/* All browser network traffic is intercepted. No production submissions. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||"playwright");
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict");
const root=path.resolve(__dirname,"../app/static");
const origin="https://booking.example.test";
const config={title:"Order a personalised storybook",intro:"Choose a story.",thanks:"Thanks for your request.",button:"Send storybook order request",
  stories:[["wedding","Wedding Storybook"],["christmas_wedding","Christmas Wedding"],["christmas","Christmas Adventure"],["holiday","Holiday Adventure"]]
    .map(([id,label])=>({id,label,enabled:true})),questions:[]};
const booking={business:{brand:"wbm",name:"Example studio"},storybooks_available:true,
  record:{kind:"wedding",status:"confirmed",title:"Example couple",event_date:"2027-05-22",venue_or_project:"Example Hall",client:{first_name:"Example"}},
  quote_preparation:{prepared:true,required_addons:[],discounts:[]},quote_ready:true,
  catalog:{packages:[{id:"p1",code:"one",name:"Package one",price:699},{id:"p2",code:"two",name:"Package two",price:899}],
    addons:[{id:"a1",name:"Another optional extra",price:30,eligible_package_codes:[]}]},
  submissions:[],invoices:[],documents:[]};
(async()=>{
const browser=await chromium.launch({executablePath:process.env.WBM_TEST_CHROME,headless:true,args:["--no-sandbox"]});
try {
for(const width of [320,390,1280]){
  const page=await browser.newPage({viewport:{width,height:820}}), posts=[], errors=[];
  page.on("pageerror",error=>errors.push(error.message));
  let fail=true, publicConfig=config, writes=0;
  await page.route("**/*",async route=>{
    const url=new URL(route.request().url()),p=url.pathname;
    if(url.origin!==origin)return route.abort();
    if(p==="/storybook-order")return route.fulfill({path:path.join(root,"storybook.html")});
    if(p.startsWith("/client/"))return route.fulfill({path:path.join(root,"client.html")});
    if(p==="/editor-test")return route.fulfill({contentType:"text/html",body:`<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1">
      <link rel="stylesheet" href="/static/storybook.css"><script>
      const api=async (url,opts)=>{const response=await fetch(url,opts);return response.json()};
      const toast=()=>{};
      </script><script src="/static/storybook-form.js"></script><script src="/static/storybook-editor.js"></script>
      <button onclick="WBMStorybookEditor.open()">Edit enquiry form</button>`});
    if(p==="/api/storybooks/form"){
      if(route.request().method()==="PUT"){publicConfig=route.request().postDataJSON();writes++;}
      return route.fulfill({json:{config:publicConfig,revision:"test-revision"}});
    }
    if(p==="/api/public/storybooks/form")return route.fulfill({json:{config:publicConfig,revision:"test-revision"}});
    if(p==="/api/client/test")return route.fulfill({json:booking});
    if(p.endsWith("/storybooks")){
      if(route.request().method()==="GET")return route.fulfill({json:[]});
      posts.push(route.request().postDataJSON());
      return route.fulfill(fail?{status:422,json:{detail:"Please try again"}}:{status:201,json:{ok:true}});
    }
    if(p.startsWith("/static/") && fs.existsSync(path.join(root,p.slice(8))))return route.fulfill({path:path.join(root,p.slice(8))});
    return route.abort();
  });
  await page.goto(origin+"/storybook-order");
  const overflow=()=>page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  assert(!(await overflow()),"public form overflows at "+width);
  await page.locator('[name="buyer_name"]').fill("Example Buyer");
  await page.locator('[name="buyer_email"]').fill("buyer@example.com");
  await page.locator('[name="theme"]').selectOption("christmas");
  assert(await page.locator('[name="wedding_date"]').isHidden());
  assert(await page.locator('[name="role"]').isHidden());
  await page.locator('[name="theme"]').selectOption("holiday");
  assert(await page.locator('[name="destination"]').isVisible());
  await page.locator('[name="theme"]').selectOption("wedding");
  await page.locator('[name="wedding_date"]').fill("2022-05-06");
  await page.locator('[name="ceremony"]').selectOption("church_separate");
  await page.locator('[name="venue"]').fill("Example Church");
  await page.locator('[name="reception"]').fill("Example Hall");
  await page.getByRole("button",{name:"Add a book for another child"}).click();
  for(const [i,child] of (await page.locator(".sb-child").all()).entries()){
    await child.locator('[name="name"]').fill("Child "+(i+1));
    await child.locator('[name="role"]').selectOption(i?"pageboy":"flower_girl");
    await child.locator('[name="hair"]').selectOption(i?"other":"blonde");
    if(i)await child.locator('[name="hair_other"]').fill("Light red");
  }
  assert.match(await page.locator("[data-sb-total]").textContent(),/£69\.98/);
  await page.locator('[name="privacy_agreed"]').check();
  await page.getByRole("button",{name:"Send storybook order request"}).click();
  await page.getByRole("alert").filter({hasText:"Please try again"}).waitFor();
  fail=false;
  await page.getByRole("button",{name:"Send storybook order request"}).click();
  await page.getByRole("heading",{name:"Thank you"}).waitFor();
  assert.equal(posts[0].submission_id,posts[1].submission_id);
  assert.equal(posts[1].details.books.length,2);
  assert(!(await overflow()),"confirmation overflows at "+width);
  await page.goto(origin+"/client/test?tab=quote");
  await page.getByRole("heading",{name:"Personalised wedding storybook"}).waitFor();
  for(const id of ["p1","p2"]){
    const choice=page.locator(`.package-card:has([name="package_id"][value="${id}"])`);
    {
      await choice.click();
      assert(await page.locator("#addon-list > :first-child").getAttribute("data-storybook-extra")!==null);
    }
  }
  await page.getByRole("button",{name:"Add a storybook"}).click();
  const dialog=page.getByRole("dialog");
  await dialog.locator('[name="theme"]').selectOption("christmas_wedding");
  assert(await dialog.locator('[name="wedding_date"]').isVisible());
  assert.equal(await dialog.locator('[name="wedding_date"]').inputValue(),"2027-05-22");
  assert.equal(await dialog.locator('[name="venue"]').inputValue(),"Example Hall");
  const rect=await dialog.boundingBox();assert(rect.x>=0&&rect.x+rect.width<=width);
  assert(!(await dialog.evaluate(el=>el.scrollWidth>el.clientWidth+1)),"dialog overflows at "+width);
  await dialog.getByRole("button",{name:"Close"}).click();
  await page.goto(origin+"/editor-test");
  await page.getByRole("button",{name:"Edit enquiry form"}).click();
  const editor=page.getByRole("dialog",{name:"Edit storybook enquiry form"});
  const editRect=await editor.boundingBox();assert(editRect.x>=0&&editRect.x+editRect.width<=width);
  assert(!(await editor.evaluate(el=>el.scrollWidth>el.clientWidth+1)),"editor overflows at "+width);
  await editor.getByLabel("Heading").fill("Choose your keepsake");
  await editor.getByRole("button",{name:"Add a story",exact:true}).click();
  await editor.getByLabel("Story name").last().fill("Birthday <Book>");
  await editor.getByRole("button",{name:"Add a question",exact:true}).click();
  await editor.getByLabel("Question",{exact:true}).fill("Birthday date");
  await editor.getByLabel("Answer type").selectOption("date");
  await editor.getByLabel("Show for").selectOption({label:"Birthday <Book>"});
  await editor.getByLabel("Answer required").check();
  await editor.getByRole("button",{name:"Preview",exact:true}).click();
  const preview=page.getByRole("dialog",{name:"Preview enquiry form"});
  await preview.getByRole("heading",{name:"Choose your keepsake"}).waitFor();
  await preview.getByLabel("Which storybook would you like?").selectOption({label:"Birthday <Book>"});
  assert(await preview.getByLabel("Birthday date").isVisible());
  assert(await preview.locator('[name="wedding_date"]').isHidden());
  await preview.getByLabel("Which storybook would you like?").selectOption("wedding");
  assert(await preview.getByLabel("Birthday date").isHidden());
  assert(await preview.getByRole("button",{name:"Send storybook order request"}).isDisabled());
  assert.equal(writes,0);
  assert.equal(posts.length,2);
  await preview.getByRole("button",{name:"Back to editing"}).click();
  await editor.getByRole("button",{name:"Publish changes"}).click();
  await editor.waitFor({state:"hidden"});
  assert.equal(writes,1);
  await page.goto(origin+"/storybook-order");
  await page.getByRole("heading",{name:"Choose your keepsake"}).waitFor();
  await page.getByLabel("Which storybook would you like?").selectOption({label:"Birthday <Book>"});
  await page.getByLabel("Birthday date").fill("2027-06-05");
  assert(await page.getByLabel("Birthday date").evaluate(el=>el.required));
  assert(!(await overflow()),"updated public form overflows at "+width);
  assert.deepEqual(errors,[]);
  await page.close();
}
console.log("Storybook editor, preview, public and couple forms verified at 320, 390 and 1280px.");
}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
