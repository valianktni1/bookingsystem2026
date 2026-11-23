/* Separate Ivory workspace. No invoice or email is created on page load. */
(() => {
  "use strict";
  const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const base="/api/ivory-quotes", money=x=>new Intl.NumberFormat("en-GB",{style:"currency",currency:"GBP"}).format(x||0);
  const ukToday=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const billingLabel={1:"Monthly",3:"Quarterly",6:"Six-monthly",12:"Annually"};
  const billingSummary=row=>row.billing?`${money(row.billing.cycle_total)} every ${row.billing.interval_months} month(s), starting ${row.billing.start_date}`:"";
  const input=(name,label,v="",extra="")=>`<label>${label}<input name="${name}" value="${esc(v)}" ${extra}></label>`;
  const val=(el,name)=>el.querySelector(`[name="${name}"]`).value.trim();
  const blank=()=>({title:"",customer:"",email:"",address:"",intro:"",terms:"Balance due before launch. No VAT charged.",opening_paid:"0",opening_paid_date:null,due_date:null,change_reason:"",lines:[{name:"",description:"",amount:"0",kind:"one_off",selected:true}]});
  let current=[];
  function dialog(title,html){
    const d=document.createElement("dialog");d.className="iq-dialog";d.setAttribute("aria-label",title);d.innerHTML=`<h2>${esc(title)}</h2>${html}`;
    document.body.append(d);d.addEventListener("close",()=>d.remove(),{once:true});d.showModal();return d;
  }
  async function perform(button,fn){button.disabled=true;try{await fn();}catch(e){toast(e.message,"error");}finally{button.disabled=false;}}
  async function edit(details=blank(),old=null,{template=false,templates=[],templateIndex=null,bookingId=null}={}){
    const isRevision=Boolean(old), d=structuredClone(details), requestId=crypto.randomUUID();
    const projects=template?[]:await api(base+"/projects");
    const validProjects=projects;
    const el=dialog(template?"Service template":isRevision?"Revise quote":"Prepare Ivory quote or invoice",`<form class="iq-form">
      ${template?input("template_name","Internal template name",d.template_name||"",'required maxlength="160"'):`<p>No invoice number is used until the quote is accepted or you record the agreement.</p>
      <label class="iq-wide">Project<select name="booking_id" ${isRevision?"disabled":""}><option value="">Create a new Ivory project</option>${validProjects.map(p=>`<option value="${esc(p.id)}" ${p.id===(bookingId||old?.booking_id)?"selected":""}>${esc(p.title)}</option>`).join("")}</select></label>
      ${input("title","Quote / invoice title",d.title,'required maxlength="160"')}${input("customer","Customer / business name",d.customer,'required maxlength="160"')}
      ${input("email","Customer email",d.email,'required type="email"')}
      <label>Billing address<textarea name="address" maxlength="1000" rows="3">${esc(d.address)}</textarea></label>`}
      <label class="iq-wide">Introduction<textarea name="intro" maxlength="2000" rows="3">${esc(d.intro)}</textarea></label>
      <div class="iq-wide" data-lines></div><button class="secondary iq-wide" type="button" data-add>Add service</button>
      ${template?"":`<label class="iq-wide">Recurring service billing<select name="billing_interval"><option value="0">One-off invoice only / monthly services quoted separately</option>${Object.entries(billingLabel).map(([v,label])=>`<option value="${v}" ${Number(d.billing?.interval_months)===Number(v)?"selected":""}>${label} — every ${v} month(s)</option>`).join("")}</select></label>
      <div class="iq-wide iq-form" data-billing>
        <p>Applies to selected Monthly services. Enter their monthly rates above; any one-off work is invoiced separately. Each recurring invoice covers the full selected period. No payment is collected automatically.</p>
        ${input("billing_start","First service period starts",d.billing?.start_date||ukToday(),'type="date" required')}
        ${input("billing_due","Payment allowance (days)",d.billing?.due_days??0,'type="number" min="0" max="90" required')}
        <label class="iq-check iq-wide"><input type="checkbox" name="issue_first_on_acceptance" ${d.billing?.issue_first_on_acceptance?"checked":""}> Issue the first invoice as soon as the quote is accepted</label>
        <p>If the first invoice is issued early, the payment allowance starts on the service start date. A 0-day allowance makes payment due on that date. Future billing dates follow the service start date.</p>
        ${input("billing_total","Agreed price for the full billing period (£)",d.billing?.cycle_total??"",'type="number" min="0.01" max="999999" step="0.01" placeholder="Leave blank to use monthly rates × months"')}
        <p data-billing-summary aria-live="polite"></p>
      </div>`}
      <label class="iq-wide">Payment terms and scope<textarea name="terms" maxlength="4000" rows="4">${esc(d.terms)}</textarea></label>
      ${template?"":`${input("due_date","Balance due date (optional)",d.due_date||"",'type="date"')}
      ${input("opening_paid","Payment already received (£)",d.opening_paid||0,'type="number" required min="0" step="0.01"')}
      ${input("opening_paid_date","Date payment received",d.opening_paid_date||"",'type="date"')}
      ${isRevision?'<label class="iq-wide">Reason for revision<textarea name="change_reason" required maxlength="1000"></textarea></label>':""}`}
      <p class="iq-wide iq-summary" aria-live="polite" data-total></p><p class="iq-error iq-wide" role="alert"></p>
      <div class="iq-actions iq-wide"><button class="primary" type="submit">${template?"Save template":isRevision?"Save new revision":"Save draft"}</button><button class="secondary" type="button" data-close>Cancel</button></div>
    </form>`);
    const form=el.querySelector("form"), lines=form.querySelector("[data-lines]"), error=form.querySelector("[role=alert]");
    function add(x){
      lines.insertAdjacentHTML("beforeend",`<fieldset class="iq-line"><legend>Service</legend><div class="iq-form">
        ${input("name","Service name",x.name,'required maxlength="160"')}
        ${input("amount","Amount (£)",x.amount,'type="number" required min="0" max="999999" step="0.01"')}
        <label class="iq-wide">Description<textarea name="description" maxlength="4000" rows="3">${esc(x.description)}</textarea></label>
        <label>Charge type<select name="kind"><option value="one_off">One-off</option><option value="included">Included / free</option><option value="monthly">Monthly (billed separately)</option></select></label>
        <label class="iq-check"><input type="checkbox" name="selected" ${x.selected?"checked":""}> Selected / agreed</label>
        <button class="secondary" type="button" data-remove>Remove service</button></div></fieldset>`);
      lines.lastElementChild.querySelector('[name="kind"]').value=x.kind;
    }
    const readLines=()=>[...lines.children].map(r=>({name:val(r,"name"),amount:val(r,"amount"),description:val(r,"description"),kind:val(r,"kind"),selected:r.querySelector('[name="selected"]').checked}));
    function update(){const rows=readLines(),total=rows.filter(x=>x.selected&&x.kind==="one_off").reduce((n,x)=>n+Number(x.amount||0),0),monthly=rows.filter(x=>x.selected&&x.kind==="monthly").reduce((n,x)=>n+Number(x.amount||0),0);
      if(!template){const months=Number(val(form,"billing_interval")),group=form.querySelector("[data-billing]");group.hidden=!months;group.querySelectorAll("input").forEach(x=>x.disabled=!months);
        const cycle=val(form,"billing_total")||monthly*months;form.querySelector("[data-billing-summary]").textContent=months?`Recurring invoice: ${money(cycle)} covers ${months} month(s). Review and send each invoice from Recurring billing.`:"";}
      form.querySelector("[data-total]").textContent=`One-off total: ${money(total)}${template?"":` · Already paid: ${money(val(form,"opening_paid"))} · Remaining: ${money(total-Number(val(form,"opening_paid")))}`} · Selected monthly services: ${money(monthly)}/month, separate.`;
      form.querySelector("[data-add]").disabled=lines.children.length>=40;}
    d.lines.forEach(add);update();form.oninput=update;form.onchange=update;
    form.querySelector("[data-add]").onclick=()=>{add({name:"",description:"",amount:"0",kind:"one_off",selected:true});update();lines.lastElementChild.querySelector("input").focus();};
    lines.onclick=e=>{if(e.target.closest("[data-remove]")){if(lines.children.length<=1){error.textContent="Keep at least one service.";return;}e.target.closest("fieldset").remove();update();}};
    if(!template && !isRevision){
      const select=form.querySelector('[name="booking_id"]');
      const applyProject=()=>{const project=validProjects.find(p=>p.id===select.value);if(!project)return;
        for(const key of ["customer","email","address"])if(project[key])form.querySelector(`[name="${key}"]`).value=project[key];};
      select.addEventListener("change",applyProject);
      if(!select.value && d.customer){const match=validProjects.filter(p=>p.customer.toLowerCase()===d.customer.toLowerCase()||p.title.toLowerCase()===d.customer.toLowerCase());if(match.length===1)select.value=match[0].id;}
      if(select.value)applyProject();
    }
    form.querySelector("[data-close]").onclick=()=>el.close();
    form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('[type="submit"]');button.disabled=true;error.textContent="";
      try{
        const shared={intro:val(form,"intro"),terms:val(form,"terms"),lines:readLines()};
        if(template){const item={...shared,name:val(form,"template_name")},items=templates.slice();if(templateIndex===null)items.push(item);else items[templateIndex]=item;await api(base+"/templates",{method:"PUT",body:JSON.stringify({items})});el.close();toast("Service template saved");await showTemplates();return;}
        const payload={request_id:requestId,booking_id:val(form,"booking_id")||null,details:{...shared,title:val(form,"title"),customer:val(form,"customer"),email:val(form,"email"),address:val(form,"address"),due_date:val(form,"due_date")||null,opening_paid:val(form,"opening_paid"),opening_paid_date:val(form,"opening_paid_date")||null,change_reason:isRevision?val(form,"change_reason"):""}};
        if(Number(val(form,"billing_interval")))payload.details.billing={interval_months:Number(val(form,"billing_interval")),start_date:val(form,"billing_start"),due_days:Number(val(form,"billing_due")),cycle_total:val(form,"billing_total")||null,issue_first_on_acceptance:form.elements.issue_first_on_acceptance.checked};
        if(Number(payload.details.opening_paid)>0&&!payload.details.opening_paid_date)throw new Error("Enter the date the payment was received.");
        await api(isRevision?base+`/${old.id}/revise`:base,{method:"POST",body:JSON.stringify(payload)});
        el.close();toast("Ivory quote draft saved");await overview();
      }catch(e){error.textContent=e.message;}finally{button.disabled=false;}
    };
  }
  async function showTemplates(){
    const data=await api(base+"/templates");
    const d=dialog("Service templates",`<p>Reusable starting points. Editing a template does not change an existing quote.</p><div class="iq-actions"><button class="primary" data-new>New template</button><button class="secondary" data-close>Close</button></div><div>${data.items.map((t,i)=>`<article class="iq-card"><h3>${esc(t.name)}</h3><p>${t.lines.length} services</p><div class="iq-actions"><button class="secondary" data-use="${i}">Use template</button><button class="secondary" data-copy="${i}">Edit template</button></div></article>`).join("")}</div>`);
    d.querySelector("[data-close]").onclick=()=>d.close();d.querySelector("[data-new]").onclick=()=>{d.close();edit(blank(),null,{template:true,templates:data.items});};
    d.querySelectorAll("[data-use]").forEach(b=>b.onclick=()=>{const t=data.items[Number(b.dataset.use)];d.close();edit({...blank(),...t,title:t.name});});
    d.querySelectorAll("[data-copy]").forEach(b=>b.onclick=()=>{const t=data.items[Number(b.dataset.copy)];d.close();edit({...blank(),...t,template_name:t.name},null,{template:true,templates:data.items,templateIndex:Number(b.dataset.copy)});});
  }
  function recordAgreement(row){
    const el=dialog(row.billing?"Record agreement and start billing":"Record agreement and create invoice",`<p>${esc(row.details.customer)} · ${money(row.total)} one-off · ${money(row.details.opening_paid)} already received.</p>${row.billing?`<p><strong>Recurring: ${esc(billingSummary(row))}.</strong> ${row.billing.issue_first_on_acceptance?"The first recurring invoice is prepared when you record this agreement.":"The first recurring invoice is prepared when the service starts."} Future invoices are prepared for review at each renewal. No emails or payments are automatic.</p>`:'<p>This creates one invoice using the next WBM number. It does not send an email.</p>'}<form class="iq-form">
      ${input("name","Who agreed?","",'required maxlength="160"')}
      <label class="iq-wide">What was agreed and when?<textarea name="note" rows="3" required maxlength="1000"></textarea></label>
      <label class="iq-check iq-wide"><input type="checkbox" required> The client has agreed to these services and prices, and I have checked any opening payment has not been recorded elsewhere.</label>
      <p class="iq-error iq-wide" role="alert"></p><div class="iq-actions iq-wide"><button class="primary" type="submit">${row.billing?"Confirm agreement & start billing":"Create agreed invoice"}</button><button class="secondary" type="button" data-close>Cancel</button></div></form>`);
    const f=el.querySelector("form");f.querySelector("[data-close]").onclick=()=>el.close();f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector('[type="submit"]');b.disabled=true;try{const accepted=await api(base+`/${row.id}/accept`,{method:"POST",body:JSON.stringify({name:val(f,"name"),note:val(f,"note"),confirmed:true})});el.close();toast(accepted.invoice?"Ivory invoice created":"Agreement recorded and recurring billing scheduled");await overview();}catch(err){f.querySelector("[role=alert]").textContent=err.message;}finally{b.disabled=false;}};
  }
  async function share(row){
    const data=await api(base+`/${row.id}/share`,{method:"POST"});
    const subject=`Your Ivory Digital quote - ${row.details.title}`;
    const body=`Hello,\n\nHere is your quotation for ${row.details.title}. Please check the agreed services, prices and payment terms using the link below. You can accept it there when you are happy to proceed.\n\n${data.url}\n\nIf you would like anything changed, just reply before accepting.\n\nThanks,\nMark`;
    const d=dialog("Client quote link",`<p>The link is ready. Copy it or review and send the email below. Creating another link replaces this one.</p>${input("url","Quote link",data.url,'readonly')}<div class="iq-actions"><button class="secondary" data-copy>Copy link</button></div>
      <form class="iq-form"><p>To: <strong>${esc(row.details.email)}</strong></p>${input("subject","Email subject",subject,'required maxlength="300"')}<label class="iq-wide">Email message<textarea name="body" required rows="9">${esc(body)}</textarea></label><p class="iq-error iq-wide" role="alert"></p><div class="iq-actions iq-wide"><button class="primary" type="submit">Send quote email</button><button class="secondary" type="button" data-close>Close</button></div></form>`);
    d.querySelector("[data-copy]").onclick=async()=>{try{await navigator.clipboard.writeText(data.url);toast("Quote link copied");}catch{d.querySelector('input[name="url"]').select();}};d.querySelector("[data-close]").onclick=()=>d.close();
    const f=d.querySelector("form");f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector('[type="submit"]');b.disabled=true;try{await api(`/api/bookings/${row.booking_id}/email-centre/send`,{method:"POST",body:JSON.stringify({mode:"manual",subject:val(f,"subject"),body:val(f,"body"),attachments:[]})});d.close();toast("Quote email sent");await overview();}catch(err){f.querySelector('[role="alert"]').textContent=err.message;}finally{b.disabled=false;}};
  }
  async function editRecurring(plan){
    const d=dialog("Edit future recurring invoices",`<p>Changes apply from the next unissued period. Issued invoices and their payments keep their original figures.</p><form class="iq-form">
      ${input("title","Service title",plan.title,'required maxlength="160"')}
      ${input("total","Price per full billing period (£)",plan.cycle_total,'type="number" required min="0.01" max="999999" step="0.01"')}
      <label class="iq-wide">Service description<textarea name="description" required maxlength="4000" rows="5">${esc(plan.description)}</textarea></label>
      <label class="iq-wide">Payment terms and scope<textarea name="terms" maxlength="4000" rows="4">${esc(plan.terms)}</textarea></label>
      <label class="iq-check iq-wide"><input type="checkbox" required> These future prices and service changes have been agreed with the customer.</label>
      <p role="alert" class="iq-error iq-wide"></p><div class="iq-actions iq-wide"><button class="primary" type="submit">Save future billing changes</button><button class="secondary" type="button" data-close>Cancel</button></div></form>`);
    d.querySelector("[data-close]").onclick=()=>d.close();const f=d.querySelector("form");f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector('[type="submit"]');b.disabled=true;try{
      await api(`/api/ivory-recurring/${plan.id}`,{method:"PUT",body:JSON.stringify({title:val(f,"title"),description:val(f,"description"),terms:val(f,"terms"),cycle_total:val(f,"total"),expected_cycle:plan.next_cycle,confirmed:true})});d.close();toast("Future recurring invoices updated");await showRecurring();
    }catch(err){f.querySelector("[role=alert]").textContent=err.message;}finally{b.disabled=false;}};
  }
  function recurringAction(plan,action){
    const descriptions={pause:"Pause future invoice generation. Existing invoices remain payable. Resuming skips paused periods and uses the next scheduled start date.",resume:"Resume at the next scheduled start date on or after today. Paused periods will not be invoiced.",cancel:"Stop this recurring schedule. Existing invoices and payments remain recorded. A new quote is needed if the service restarts.",generate:`Create one invoice for the next scheduled period starting ${plan.next_billing_date}. If this is a missed period, check the service was supplied before continuing. No email or payment is automatic.`};
    const d=dialog("Review recurring billing action",`<p>${esc(plan.customer)} · ${esc(plan.title)}</p><p>${esc(descriptions[action])}</p><div class="iq-actions"><button class="primary" data-confirm>${esc({pause:"Pause schedule",resume:"Resume schedule",cancel:"Cancel schedule",generate:"Create next invoice"}[action])}</button><button class="secondary" data-close>Back</button></div><p role="alert" class="iq-error"></p>`);
    d.querySelector("[data-close]").onclick=()=>d.close();d.querySelector("[data-confirm]").onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{const result=await api(`/api/ivory-recurring/${plan.id}/action`,{method:"POST",body:JSON.stringify({action,expected_cycle:plan.next_cycle})});d.close();toast(result.invoice_number?`${result.invoice_number} created — review before sending`:"Recurring schedule updated");await showRecurring();}catch(err){d.querySelector("[role=alert]").textContent=err.message;}finally{b.disabled=false;}};
  }
  async function showRecurring(){
    const plans=await api("/api/ivory-recurring");
    const d=dialog("Recurring billing",`<p>Invoices are prepared automatically for active schedules when each period starts. Review their PDFs and use Email invoice when ready. Payments are recorded separately when received.</p><div class="iq-actions"><button class="secondary" data-refresh>Refresh</button><button class="secondary" data-close>Close</button></div>
      ${plans.length?plans.map(p=>`<article class="iq-card"><h3>${esc(p.customer)} — ${esc(p.title)}</h3><p><strong>${money(p.cycle_total)} ${esc(billingLabel[p.interval_months])?.toLowerCase()}</strong> · ${esc(p.status)}</p><p>Next period starts: ${esc(p.next_billing_date)} · Payment due ${p.due_days} day(s) after issue.</p>${p.last_error?`<p role="alert" class="iq-error">${esc(p.last_error)}</p>`:""}
      <div class="iq-actions">${p.status!=="cancelled"?`<button class="secondary" data-plan="${p.id}" data-action="edit">Edit future invoices</button><button class="secondary" data-plan="${p.id}" data-action="${p.status==="paused"?"resume":"pause"}">${p.status==="paused"?"Resume":"Pause"}</button><button class="secondary" data-plan="${p.id}" data-action="cancel">Cancel schedule</button>${p.status==="active"?`<button class="secondary" data-plan="${p.id}" data-action="generate" ${p.next_billing_date>ukToday()?"disabled":""}>Create next invoice</button>`:""}`:""}<button class="secondary" data-project="${p.booking_id}">Project &amp; payments</button></div>
      ${p.invoices.map(i=>`<section class="iq-recurring-invoice"><p><strong>${esc(i.number)}</strong> · ${esc(i.period_start)} to ${esc(i.period_end)} · ${esc(i.status)} · Balance ${money(i.balance)}</p>${i.id?`<div class="iq-actions"><a class="secondary" href="/api/invoices/${esc(i.id)}/pdf" target="_blank" rel="noopener">Invoice PDF</a><button class="secondary" data-email="${esc(i.id)}">Email invoice</button></div>`:""}</section>`).join("")||"<p>No invoice is due yet.</p>"}</article>`).join(""):"<p>No recurring schedules yet. Choose New recurring invoice, or add recurring billing to a quote with selected Monthly services.</p>"}`);
    d.querySelector("[data-close]").onclick=()=>d.close();d.querySelector("[data-refresh]").onclick=()=>{d.close();showRecurring();};
    d.querySelectorAll("[data-plan]").forEach(b=>b.onclick=()=>{const p=plans.find(x=>x.id===b.dataset.plan);d.close();if(b.dataset.action==="edit")editRecurring(p);else recurringAction(p,b.dataset.action);});
    d.querySelectorAll("[data-email]").forEach(b=>b.onclick=()=>{d.close();emailInvoice(b.dataset.email);});
    d.querySelectorAll("[data-project]").forEach(b=>b.onclick=()=>{d.close();openDrawer(b.dataset.project,"Payments");});
  }
  async function overview(){
    const host=document.querySelector("#content");host.innerHTML='<section class="panel iq-workspace"><h2>Ivory quotes &amp; invoices</h2><p>Prepare a quote, record agreement and manage the invoice. All new invoices use the shared WBM number sequence.</p><div class="iq-actions"><button class="primary" data-new>New quote</button><button class="secondary" data-recurring-new>New recurring invoice</button><button class="secondary" data-schedules>Recurring billing</button><button class="secondary" data-starter>Prepare Andy’s agreed invoice</button><button class="secondary" data-templates>Service templates</button></div><div data-offers>Loading…</div></section>';
    host.querySelector("[data-recurring-new]").onclick=()=>edit({...blank(),billing:{interval_months:1,start_date:ukToday(),due_days:0},lines:[{name:"",description:"",amount:"0",kind:"monthly",selected:true}]});
    host.querySelector("[data-schedules]").onclick=e=>perform(e.currentTarget,showRecurring);
    host.querySelector("[data-new]").onclick=()=>edit();host.querySelector("[data-starter]").onclick=e=>perform(e.currentTarget,async()=>edit(await api(base+"/starter")));host.querySelector("[data-templates]").onclick=e=>perform(e.currentTarget,showTemplates);
    try{
      current=await api(base);if(!host.isConnected||state.view!=="ivoryquotes")return;
      host.querySelector("[data-offers]").innerHTML=current.map(row=>`<article class="iq-card"><h3>${esc(row.details.customer)}</h3><p>${esc(row.reference)} · ${esc(row.status)} · ${esc(row.details.title)}</p><p><strong>${money(row.total)}</strong> one-off${row.monthly?` · ${money(row.monthly)}/month separately`:""}</p>
        ${row.billing?`<p><strong>Recurring: ${esc(billingSummary(row))}</strong>${row.recurring?` · ${esc(row.recurring.status)} · Next billing ${esc(row.recurring.next_billing_date)}`:" · Starts on acceptance"}</p>`:""}
        ${row.details.change_reason?`<p>Revision: ${esc(row.details.change_reason)}</p>`:""}
        ${row.invoice?`<p>Invoice <strong>${esc(row.invoice.number)}</strong> · Paid ${money(row.invoice.paid)} · Remaining <strong>${money(row.invoice.balance)}</strong></p>`:""}
        <div class="iq-actions"><a class="secondary" href="${base}/${row.id}/pdf" target="_blank" rel="noopener">Quote PDF</a>
        ${["draft","shared"].includes(row.status)?`<a class="secondary" href="${base}/${row.id}/invoice-preview.pdf" target="_blank" rel="noopener">Invoice preview</a><button class="secondary" data-act="revise" data-id="${row.id}">Revise quote</button><button class="secondary" data-act="share" data-id="${row.id}">Get client acceptance link</button><button class="primary" data-act="agree" data-id="${row.id}">${row.billing?"Record agreement &amp; start billing":"Record agreement &amp; create invoice"}</button>`:""}
        ${row.invoice?`<a class="secondary" href="/api/invoices/${row.invoice.id}/pdf" target="_blank" rel="noopener">Invoice PDF</a><button class="secondary" data-act="email" data-id="${row.id}">Email invoice</button><button class="secondary" data-act="add" data-id="${row.id}">Quote additional services</button><button class="secondary" data-act="project" data-id="${row.id}">Project &amp; payments</button>`:""}</div></article>`).join("")||'<p>No Ivory quotes yet. Start with a service template or Andy’s agreed invoice.</p>';
      host.querySelectorAll("[data-act]").forEach(b=>b.onclick=()=>perform(b,async()=>{const row=current.find(r=>r.id===b.dataset.id);if(b.dataset.act==="revise")return edit(row.details,row);if(b.dataset.act==="agree")return recordAgreement(row);if(b.dataset.act==="share")return share(row);if(b.dataset.act==="email")return emailInvoice(row.invoice.id);if(b.dataset.act==="project")return openDrawer(row.booking_id,"Payments");if(b.dataset.act==="add")return edit({...blank(),title:"Additional services",customer:row.details.customer,email:row.details.email,address:row.details.address},null,{bookingId:row.booking_id});}));
    }catch(e){if(host.isConnected)host.querySelector("[data-offers]").textContent=e.message;}
  }
  const previous=render;render=function(...args){if(state.view!=="ivoryquotes")return previous.apply(this,args);document.querySelector("#page-eyebrow").textContent="IVORY DIGITAL";document.querySelector("#page-title").textContent="Quotes & invoices";document.querySelector("#page-subtitle").textContent="Templates, agreements and payments";overview();};
})();
