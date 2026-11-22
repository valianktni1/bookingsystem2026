/* Separate Ivory workspace. No invoice or email is created on page load. */
(() => {
  "use strict";
  const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const base="/api/ivory-quotes", money=x=>new Intl.NumberFormat("en-GB",{style:"currency",currency:"GBP"}).format(x||0);
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
    const el=dialog("Record agreement and create invoice",`<p>${esc(row.details.customer)} · ${money(row.total)} total · ${money(row.details.opening_paid)} already received.</p><p>This creates one invoice using the next WBM number. It does not send an email.</p><form class="iq-form">
      ${input("name","Who agreed?","",'required maxlength="160"')}
      <label class="iq-wide">What was agreed and when?<textarea name="note" rows="3" required maxlength="1000"></textarea></label>
      <label class="iq-check iq-wide"><input type="checkbox" required> The client has agreed to these services and prices, and I have checked any opening payment has not been recorded elsewhere.</label>
      <p class="iq-error iq-wide" role="alert"></p><div class="iq-actions iq-wide"><button class="primary" type="submit">Create agreed invoice</button><button class="secondary" type="button" data-close>Cancel</button></div></form>`);
    const f=el.querySelector("form");f.querySelector("[data-close]").onclick=()=>el.close();f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector('[type="submit"]');b.disabled=true;try{await api(base+`/${row.id}/accept`,{method:"POST",body:JSON.stringify({name:val(f,"name"),note:val(f,"note"),confirmed:true})});el.close();toast("Ivory invoice created");await overview();}catch(err){f.querySelector("[role=alert]").textContent=err.message;}finally{b.disabled=false;}};
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
  async function overview(){
    const host=document.querySelector("#content");host.innerHTML='<section class="panel iq-workspace"><h2>Ivory quotes &amp; invoices</h2><p>Prepare a quote, record agreement and manage the invoice. All new invoices use the shared WBM number sequence.</p><div class="iq-actions"><button class="primary" data-new>New quote</button><button class="secondary" data-starter>Prepare Andy’s agreed invoice</button><button class="secondary" data-templates>Service templates</button></div><div data-offers>Loading…</div></section>';
    host.querySelector("[data-new]").onclick=()=>edit();host.querySelector("[data-starter]").onclick=e=>perform(e.currentTarget,async()=>edit(await api(base+"/starter")));host.querySelector("[data-templates]").onclick=e=>perform(e.currentTarget,showTemplates);
    try{
      current=await api(base);if(!host.isConnected||state.view!=="ivoryquotes")return;
      host.querySelector("[data-offers]").innerHTML=current.map(row=>`<article class="iq-card"><h3>${esc(row.details.customer)}</h3><p>${esc(row.reference)} · ${esc(row.status)} · ${esc(row.details.title)}</p><p><strong>${money(row.total)}</strong> one-off${row.monthly?` · ${money(row.monthly)}/month separately`:""}</p>
        ${row.details.change_reason?`<p>Revision: ${esc(row.details.change_reason)}</p>`:""}
        ${row.invoice?`<p>Invoice <strong>${esc(row.invoice.number)}</strong> · Paid ${money(row.invoice.paid)} · Remaining <strong>${money(row.invoice.balance)}</strong></p>`:""}
        <div class="iq-actions"><a class="secondary" href="${base}/${row.id}/pdf" target="_blank" rel="noopener">Quote PDF</a>
        ${["draft","shared"].includes(row.status)?`<a class="secondary" href="${base}/${row.id}/invoice-preview.pdf" target="_blank" rel="noopener">Invoice preview</a><button class="secondary" data-act="revise" data-id="${row.id}">Revise quote</button><button class="secondary" data-act="share" data-id="${row.id}">Get client acceptance link</button><button class="primary" data-act="agree" data-id="${row.id}">Record agreement &amp; create invoice</button>`:""}
        ${row.invoice?`<a class="secondary" href="/api/invoices/${row.invoice.id}/pdf" target="_blank" rel="noopener">Invoice PDF</a><button class="secondary" data-act="email" data-id="${row.id}">Email invoice</button><button class="secondary" data-act="add" data-id="${row.id}">Quote additional services</button><button class="secondary" data-act="project" data-id="${row.id}">Project &amp; payments</button>`:""}</div></article>`).join("")||'<p>No Ivory quotes yet. Start with a service template or Andy’s agreed invoice.</p>';
      host.querySelectorAll("[data-act]").forEach(b=>b.onclick=()=>perform(b,async()=>{const row=current.find(r=>r.id===b.dataset.id);if(b.dataset.act==="revise")return edit(row.details,row);if(b.dataset.act==="agree")return recordAgreement(row);if(b.dataset.act==="share")return share(row);if(b.dataset.act==="email")return emailInvoice(row.invoice.id);if(b.dataset.act==="project")return openDrawer(row.booking_id,"Payments");if(b.dataset.act==="add")return edit({...blank(),title:"Additional services",customer:row.details.customer,email:row.details.email,address:row.details.address},null,{bookingId:row.booking_id});}));
    }catch(e){if(host.isConnected)host.querySelector("[data-offers]").textContent=e.message;}
  }
  const previous=render;render=function(...args){if(state.view!=="ivoryquotes")return previous.apply(this,args);document.querySelector("#page-eyebrow").textContent="IVORY DIGITAL";document.querySelector("#page-title").textContent="Quotes & invoices";document.querySelector("#page-subtitle").textContent="Templates, agreements and payments";overview();};
})();
