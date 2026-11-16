/* Shared order fields: public form, secure client area, and admin review. */
(() => {
  "use strict";
  const esc = value => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const price = new Intl.NumberFormat("en-GB", {style:"currency",currency:"GBP"});
  const sample = "https://perfectweddingsbymark.uk/personalised-wedding-storybooks/";
  const role = {flower_girl:"Flower girl",pageboy:"Pageboy",child:"Child"};
  const themes = {wedding:"Wedding Storybook",christmas_wedding:"Christmas Wedding",christmas:"Christmas Adventure",holiday:"Holiday Adventure"};
  const isWedding = theme => theme === "wedding" || theme === "christmas_wedding";
  const hair = {black:"Black",dark_brown:"Dark brown",light_brown:"Light brown",blonde:"Blonde",red_ginger:"Red or ginger",other:"Other"};
  const ceremony = {one_venue:"All day at one venue",church_separate:"Church ceremony with a separate reception",other:"Other ceremony and reception arrangement"};
  const options = (choices, selected) => '<option value="">Please choose</option>' + Object.entries(choices).map(([k,v]) => `<option value="${k}" ${k===selected?"selected":""}>${esc(v)}</option>`).join("");
  const input = (name,label,value="",opts="") => `<label>${label}<input name="${name}" value="${esc(value)}" ${opts}></label>`;
  const child = (d={}) => `<fieldset class="sb-child"><legend>Child's book</legend><div class="sb-grid">
    ${input("name","Child’s first name",d.name,'required maxlength="80" placeholder="Exact spelling for the cover"')}
    <label data-sb-wedding-role>Wedding role<select name="role" required>${options({flower_girl:role.flower_girl,pageboy:role.pageboy},d.role)}</select></label>
    <label>What colour is their hair?<select name="hair" required>${options(hair,d.hair)}</select></label>
    <label data-sb-other-hair hidden>Hair colour<input name="hair_other" maxlength="80" value="${esc(d.hair_other)}"></label>
    ${input("quantity","Number of identical copies",d.quantity ?? 1,'type="number" min="1" max="24" step="1" required')}
    <label class="sb-wide">Dedication and sign-off (optional)<textarea name="dedication" maxlength="600" rows="3" placeholder="For example, Love, Mum and Dad">${esc(d.dedication)}</textarea></label>
    </div><button type="button" class="sb-secondary" data-sb-remove>Remove this child</button></fieldset>`;
  function fields(d={}, buyer=null, admin=false, config=null) {
    const choices=config ? Object.fromEntries(config.stories.filter(story=>story.enabled).map(story=>[story.id,story.label])) :
      (admin && d.theme_title ? {...themes,[d.theme]:d.theme_title} : themes);
    const questions=(config?.questions || []).map(q=>{
      const attrs=`name="sb_q_${esc(q.id)}" data-sb-answer`;
      const field=q.kind==="paragraph" ? `<textarea ${attrs} maxlength="1000" rows="3"></textarea>` :
        `<input ${attrs} type="${q.kind==="date"?"date":"text"}" maxlength="160">`;
      return `<label class="sb-wide" data-sb-question="${esc(q.id)}" hidden>${esc(q.label)}${q.required?"":" (optional)"}${field}</label>`;
    }).join("");
    return `<div class="sb-grid">
    <label class="sb-wide">Which storybook would you like?<select name="theme" required>${options(choices,d.theme ?? (admin ? "wedding" : ""))}</select></label>
    <p class="sb-wide" data-sb-theme-help></p>
    ${buyer ? input("buyer_name","Your name",buyer.buyer_name,'required maxlength="160" autocomplete="name"') + input("buyer_email",admin?"Billing email":"Your email",buyer.buyer_email,'type="email" required maxlength="254" autocomplete="email"') : ""}
    <div class="sb-conditional" data-sb-wedding hidden>
    ${input("wedding_date","Wedding date",d.wedding_date,'type="date" required')}
    <label>What kind of ceremony?<select name="ceremony" required>${options(ceremony,d.ceremony)}</select></label>
    <label data-sb-separate hidden><span><input type="checkbox" name="separate_venues" ${d.separate_venues?"checked":""}> The reception was or is at a different venue</span></label>
    <label><span data-sb-venue-label>Wedding venue name</span><input name="venue" required maxlength="160" value="${esc(d.venue)}"></label>
    <label data-sb-reception hidden>Reception venue name<input name="reception" maxlength="160" value="${esc(d.reception)}"></label>
    </div><div class="sb-wide" data-sb-destination hidden>${input("destination","Holiday destination (optional)",d.destination,'maxlength="160"')}</div>
    ${input("needed_by","When do you need the book? (optional)",d.needed_by,'type="date"')}
    <label class="sb-wide"><span><input type="checkbox" name="gift" ${d.gift?"checked":""}> I’m ordering this as a gift</span></label>
    ${questions}</div><div data-sb-children>${(d.books?.length ? d.books : [{}]).map(child).join("")}</div>
    <div class="sb-actions"><button type="button" class="sb-secondary" data-sb-add>Add a book for another child</button>
    <strong data-sb-total aria-live="polite"></strong></div>`;
  }
  function wire(form, questions=[]) {
    const children = form.querySelector("[data-sb-children]");
    const add = form.querySelector("[data-sb-add]");
    const update = () => {
      const theme = form.querySelector('[name="theme"]').value;
      const wedding = isWedding(theme);
      for(const q of questions){
        const row=form.querySelector(`[data-sb-question="${q.id}"]`);
        const visible=Boolean(theme) && (!q.story || q.story===theme);
        row.hidden=!visible;
        const field=row.querySelector("[data-sb-answer]");
        field.disabled=!visible;field.required=visible && q.required;
      }
      form.querySelector("[data-sb-wedding]").hidden = !wedding;
      for (const key of ["wedding_date","ceremony","venue"]) {
        const field=form.querySelector(`[name="${key}"]`); field.disabled=!wedding;field.required=wedding;
      }
      form.querySelector("[data-sb-destination]").hidden = theme !== "holiday";
      form.querySelector("[data-sb-theme-help]").textContent = theme === "wedding" ? "£34.99 per book including UK delivery." : theme ? "Mark will confirm the price and delivery date before you pay." : "Choose a story to see the details needed.";
      const arrangement = form.querySelector('[name="ceremony"]').value;
      const separate = wedding && (arrangement === "church_separate" || arrangement === "other" && form.querySelector('[name="separate_venues"]').checked);
      form.querySelector("[data-sb-separate]").hidden = arrangement !== "other";
      form.querySelector("[data-sb-reception]").hidden = !separate;
      form.querySelector('[name="reception"]').required = separate;
      form.querySelector("[data-sb-venue-label]").textContent = separate ? "Ceremony venue name" : "Wedding venue name";
      const list = [...children.querySelectorAll(".sb-child")];
      let n = 0;
      list.forEach((block,i) => {
        block.querySelector("legend").textContent = list.length === 1 ? "Child’s book" : `Child ${i+1}’s book`;
        const roleSelect=block.querySelector('[name="role"]');
        block.querySelector("[data-sb-wedding-role]").hidden=!wedding;
        roleSelect.disabled=!wedding;roleSelect.required=wedding;
        const isOther = block.querySelector('[name="hair"]').value === "other";
        block.querySelector("[data-sb-other-hair]").hidden = !isOther;
        block.querySelector('[name="hair_other"]').required = isOther;
        block.querySelector("[data-sb-remove]").hidden = list.length === 1;
        n += Number(block.querySelector('[name="quantity"]').value) || 0;
      });
      add.disabled = list.length >= 12;
      form.querySelector("[data-sb-total]").textContent = theme === "wedding" ? `${price.format(n * 3499 / 100)} including UK delivery` : theme ? `${n} cop${n===1?"y":"ies"} · price to confirm` : "";
    };
    add.onclick = () => {children.insertAdjacentHTML("beforeend",child());update();children.lastElementChild.querySelector("input").focus();};
    children.onclick = event => {const button = event.target.closest("[data-sb-remove]");if(button && children.children.length > 1){button.closest("fieldset").remove();update();add.focus();}};
    form.addEventListener("input",update);
    form.addEventListener("change",update);
    update();
  }
  const val = (root,name) => root.querySelector(`[name="${name}"]`)?.value.trim() || null;
  function details(form) {
    const theme=val(form,"theme"), wedding=isWedding(theme);
    return {theme,wedding_date:wedding?val(form,"wedding_date"):null,ceremony:wedding?val(form,"ceremony"):null,
      venue:wedding?val(form,"venue"):null,separate_venues:wedding&&form.querySelector('[name="separate_venues"]').checked,
      reception:wedding?val(form,"reception"):null,destination:theme==="holiday"?val(form,"destination"):null,needed_by:val(form,"needed_by"),gift:form.querySelector('[name="gift"]').checked,
      books:[...form.querySelectorAll(".sb-child")].map(block => ({
        name:val(block,"name"),role:wedding?val(block,"role"):"child",hair:val(block,"hair"),hair_other:val(block,"hair_other"),
        dedication:val(block,"dedication"),quantity:Number(val(block,"quantity"))
      }))};
  }
  const consent = `<label class="sb-consent"><span><input name="privacy_agreed" type="checkbox" required> I’ve read the <a href="https://perfectweddingsbymark.uk/terms-privacy/" target="_blank" rel="noopener">privacy information</a> and agree to these details being used to process my request.</span></label>`;
  const success = "Thanks, I’ve got your storybook request. I’ll reply by email to confirm the details, delivery timing and how to pay.";
  function publicContent(config) {
    const intro=config.intro.split(/\n[ \t]*\n/).map(part=>`<p>${esc(part)}</p>`).join("");
    const fixedPrice=config.stories.some(story=>story.id==="wedding"&&story.enabled);
    return `<h1>${esc(config.title)}</h1>${intro}${fixedPrice?'<p><strong>The classic wedding book is £34.99 including UK delivery.</strong></p>':""}
      <form id="storybook-request">${fields({}, {}, false, config)}${consent}
      <label class="sb-website" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label>
      <p class="sb-error" role="alert" data-sb-error></p><button class="sb-primary" type="submit">${esc(config.button)}</button></form>`;
  }
  const statuses = {new:"New request",invoiced:"Invoiced",paid:"Paid · ready to prepare",sent_to_print:"Sent to print",dispatched:"Dispatched",cancelled:"Cancelled"};
  async function submit(url,payload) {
    const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const json=await response.json().catch(()=>({}));
    if(!response.ok) throw new Error(Array.isArray(json.detail)?json.detail.map(x=>x.msg.replace(/^Value error, /,"")).join("; "):json.detail||"Couldn’t save your request. Please try again.");
    return json;
  }
  function requestForm(form,url,{publicOrder=false,config,revision,onSuccess}={}) {
    const submission_id=crypto.randomUUID();
    wire(form,config?.questions);
    form.onsubmit=async event=>{
      event.preventDefault();
      const button=form.querySelector("button[type=submit]"),error=form.querySelector("[data-sb-error]");
      const buttonLabel=button.textContent;
      button.disabled=true;error.textContent="";button.textContent="Sending…";
      try {
        const payload={submission_id,details:details(form),privacy_agreed:form.querySelector('[name="privacy_agreed"]').checked,website:val(form,"website")||""};
        if(publicOrder) {payload.buyer_name=val(form,"buyer_name");payload.buyer_email=val(form,"buyer_email");}
        if(config){
          payload.form_revision=revision;
          payload.answers=Object.fromEntries([...form.querySelectorAll("[data-sb-answer]:enabled")]
            .filter(field=>field.value.trim()).map(field=>[field.name.slice(5),field.value.trim()]));
        }
        await submit(url,payload);
      } catch(err) {error.textContent=err.message;button.disabled=false;button.textContent=buttonLabel;return;}
      onSuccess();
    };
  }
  window.WBMStorybooks={fields,wire,details,val,esc,input,role,hair,ceremony,themes,isWedding,consent,success,statuses,sample,requestForm,publicContent,price};
})();
