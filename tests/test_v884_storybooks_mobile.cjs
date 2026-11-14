/* All browser network traffic is intercepted. No production submissions. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||"playwright");
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict");
const root=path.resolve(__dirname,"../app/static");
const origin="https://booking.example.test";
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
  let fail=true;
  await page.route("**/*",async route=>{
    const url=new URL(route.request().url()),p=url.pathname;
    if(url.origin!==origin)return route.abort();
    if(p==="/storybook-order")return route.fulfill({path:path.join(root,"storybook.html")});
    if(p.startsWith("/client/"))return route.fulfill({path:path.join(root,"client.html")});
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
  assert.equal(await dialog.locator('[name="wedding_date"]').inputValue(),"2027-05-22");
  assert.equal(await dialog.locator('[name="venue"]').inputValue(),"Example Hall");
  const rect=await dialog.boundingBox();assert(rect.x>=0&&rect.x+rect.width<=width);
  assert(!(await dialog.evaluate(el=>el.scrollWidth>el.clientWidth+1)),"dialog overflows at "+width);
  await dialog.getByRole("button",{name:"Close"}).click();
  assert.deepEqual(errors,[]);
  await page.close();
}
console.log("Storybook public and couple forms verified at 320, 390 and 1280px.");
}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
