/* Shared order fields: public form, secure client area, and admin review. */
(() => {
  "use strict";
  const esc = value => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const price = new Intl.NumberFormat("en-GB", {style:"currency",currency:"GBP"});
  const sample = "https://perfectweddingsbymark.uk/personalised-wedding-storybooks/";
  const role = {flower_girl:"Flower girl",pageboy:"Pageboy"};
  const hair = {black:"Black",dark_brown:"Dark brown",light_brown:"Light brown",blonde:"Blonde",red_ginger:"Red or ginger",other:"Other"};
  const ceremony = {one_venue:"All day at one venue",church_separate:"Church ceremony with a separate reception",other:"Other ceremony and reception arrangement"};
  const options = (choices, selected) => '<option value="">Please choose</option>' + Object.entries(choices).map(([k,v]) => `<option value="${k}" ${k===selected?"selected":""}>${v}</option>`).join("");
  const input = (name,label,value="",opts="") => `<label>${label}<input name="${name}" value="${esc(value)}" ${opts}></label>`;
  const child = (d={}) => `<fieldset class="sb-child"><legend>Child's book</legend><div class="sb-grid">
    ${input("name","Child’s first name",d.name,'required maxlength="80" placeholder="Exact spelling for the cover"')}
    <label>Who is the book for?<select name="role" required>${options(role,d.role)}</select></label>
    <label>What colour is their hair?<select name="hair" required>${options(hair,d.hair)}</select></label>
    <label data-sb-other-hair hidden>Hair colour<input name="hair_other" maxlength="80" value="${esc(d.hair_other)}"></label>
    ${input("quantity","Number of identical copies",d.quantity ?? 1,'type="number" min="1" max="24" step="1" required')}
    <label class="sb-wide">Dedication and sign-off (optional)<textarea name="dedication" maxlength="600" rows="3" placeholder="For example, Love, Mum and Dad">${esc(d.dedication)}</textarea></label>
    </div><button type="button" class="sb-secondary" data-sb-remove>Remove this child</button></fieldset>`;
  function fields(d={}, buyer=null, admin=false) {
    return `<div class="sb-grid">
    ${buyer ? input("buyer_name","Your name",buyer.buyer_name,'required maxlength="160" autocomplete="name"') + input("buyer_email",admin?"Billing email":"Your email",buyer.buyer_email,'type="email" required maxlength="254" autocomplete="email"') : ""}
    ${input("wedding_date","Wedding date",d.wedding_date,'type="date" required')}
    <label>What kind of ceremony?<select name="ceremony" required>${options(ceremony,d.ceremony)}</select></label>
    <label data-sb-separate hidden><span><input type="checkbox" name="separate_venues" ${d.separate_venues?"checked":""}> The reception was or is at a different venue</span></label>
    <label><span data-sb-venue-label>Wedding venue name</span><input name="venue" required maxlength="160" value="${esc(d.venue)}"></label>
    <label data-sb-reception hidden>Reception venue name<input name="reception" maxlength="160" value="${esc(d.reception)}"></label>
    ${input("needed_by","When do you need the book? (optional)",d.needed_by,'type="date"')}
    <label class="sb-wide"><span><input type="checkbox" name="gift" ${d.gift?"checked":""}> I’m ordering this as a gift</span></label>
    </div><div data-sb-children>${(d.books?.length ? d.books : [{}]).map(child).join("")}</div>
    <div class="sb-actions"><button type="button" class="sb-secondary" data-sb-add>Add a book for another child</button>
    <strong data-sb-total aria-live="polite"></strong></div>`;
  }
  function wire(form) {
    const children = form.querySelector("[data-sb-children]");
    const add = form.querySelector("[data-sb-add]");
    const update = () => {
      const arrangement = form.querySelector('[name="ceremony"]').value;
      const separate = arrangement === "church_separate" || arrangement === "other" && form.querySelector('[name="separate_venues"]').checked;
      form.querySelector("[data-sb-separate]").hidden = arrangement !== "other";
      form.querySelector("[data-sb-reception]").hidden = !separate;
      form.querySelector('[name="reception"]').required = separate;
      form.querySelector("[data-sb-venue-label]").textContent = separate ? "Ceremony venue name" : "Wedding venue name";
      const list = [...children.querySelectorAll(".sb-child")];
      let n = 0;
      list.forEach((block,i) => {
        block.querySelector("legend").textContent = list.length === 1 ? "Child’s book" : `Child ${i+1}’s book`;
        const isOther = block.querySelector('[name="hair"]').value === "other";
        block.querySelector("[data-sb-other-hair]").hidden = !isOther;
        block.querySelector('[name="hair_other"]').required = isOther;
        block.querySelector("[data-sb-remove]").hidden = list.length === 1;
        n += Number(block.querySelector('[name="quantity"]').value) || 0;
      });
      add.disabled = list.length >= 12;
      form.querySelector("[data-sb-total]").textContent = `${price.format(n * 3499 / 100)} including UK delivery`;
    };
    add.onclick = () => {children.insertAdjacentHTML("beforeend",child());update();children.lastElementChild.querySelector("input").focus();};
    children.onclick = event => {const button = event.target.closest("[data-sb-remove]");if(button && children.children.length > 1){button.closest("fieldset").remove();update();add.focus();}};
    form.addEventListener("input",update);
    form.addEventListener("change",update);
    update();
  }
  const val = (root,name) => root.querySelector(`[name="${name}"]`)?.value.trim() || null;
  function details(form) {
    return {wedding_date:val(form,"wedding_date"),ceremony:val(form,"ceremony"),
      venue:val(form,"venue"),separate_venues:form.querySelector('[name="separate_venues"]').checked,
      reception:val(form,"reception"),needed_by:val(form,"needed_by"),gift:form.querySelector('[name="gift"]').checked,
      books:[...form.querySelectorAll(".sb-child")].map(block => ({
        name:val(block,"name"),role:val(block,"role"),hair:val(block,"hair"),hair_other:val(block,"hair_other"),
        dedication:val(block,"dedication"),quantity:Number(val(block,"quantity"))
      }))};
  }
  const consent = `<label class="sb-consent"><span><input name="privacy_agreed" type="checkbox" required> I’ve read the <a href="https://perfectweddingsbymark.uk/terms-privacy/" target="_blank" rel="noopener">privacy information</a> and agree to these details being used to process my request.</span></label>`;
  const success = "Thanks, I’ve got your storybook request. I’ll reply by email to confirm the details, delivery timing and how to pay.";
  const statuses = {new:"New request",invoiced:"Invoiced",paid:"Paid · ready to prepare",sent_to_print:"Sent to print",dispatched:"Dispatched",cancelled:"Cancelled"};
  async function submit(url,payload) {
    const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const json=await response.json().catch(()=>({}));
    if(!response.ok) throw new Error(Array.isArray(json.detail)?json.detail.map(x=>x.msg.replace(/^Value error, /,"")).join("; "):json.detail||"Couldn’t save your request. Please try again.");
    return json;
  }
  function requestForm(form,url,{publicOrder=false,onSuccess}={}) {
    const submission_id=crypto.randomUUID();
    wire(form);
    form.onsubmit=async event=>{
      event.preventDefault();
      const button=form.querySelector("button[type=submit]"),error=form.querySelector("[data-sb-error]");
      button.disabled=true;error.textContent="";button.textContent="Sending…";
      try {
        const payload={submission_id,details:details(form),privacy_agreed:form.querySelector('[name="privacy_agreed"]').checked,website:val(form,"website")||""};
        if(publicOrder) {payload.buyer_name=val(form,"buyer_name");payload.buyer_email=val(form,"buyer_email");}
        await submit(url,payload);
      } catch(err) {error.textContent=err.message;button.disabled=false;button.textContent="Send storybook order request";return;}
      onSuccess();
    };
  }
  window.WBMStorybooks={fields,wire,details,val,esc,input,role,hair,ceremony,consent,success,statuses,sample,requestForm,price};
})();
