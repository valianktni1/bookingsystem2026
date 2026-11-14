(() => {
  "use strict";
  const s=window.WBMStorybooks;
  const esc=s.esc, today=()=>new Intl.DateTimeFormat("sv-SE",{timeZone:"Europe/London"}).format(new Date());
  const date=value=>value?new Intl.DateTimeFormat("en-GB",{day:"numeric",month:"short",year:"numeric"}).format(new Date(value+"T12:00:00")):"Not specified";
  let page=0;
  async function run(action,button) {
    button.disabled=true;
    try {await action();}
    catch(error){toast(error.message,"error");}
    finally{button.disabled=false;}
  }
  function payment(order, reload) {
    const i=order.invoice;
    showModal("Record storybook payment",`
      <label>Amount<input id="sb-payment-amount" type="number" min="0.01" step="0.01" max="${i.balance}" value="${i.balance}" required></label>
      <label>Date received<input id="sb-payment-date" type="date" value="${today()}" required></label>
      <label>Payment method<select id="sb-payment-type"><option value="bank_transfer">Bank transfer</option><option value="cash">Cash</option></select></label>
      <label>Reference<input id="sb-payment-reference" maxlength="120" value="${esc(i.number)}"></label>`,
      async()=>{await api(`/api/invoices/${i.id}/payments`,{method:"POST",body:JSON.stringify({
        amount:value("#sb-payment-amount"),paid_date:value("#sb-payment-date"),payment_type:value("#sb-payment-type"),
        reference:value("#sb-payment-reference")||null
      })});closeModal();toast("Storybook payment recorded");await reload();},
      "This records payment against the book invoice only.");
  }
  function edit(order,reload) {
    const dialog=document.createElement("dialog");
    dialog.className="sb-dialog";
    dialog.setAttribute("aria-labelledby","sb-review-title");
    dialog.innerHTML=`<h2 id="sb-review-title">Review storybook request</h2>
    <form>${s.fields(order.details,order,true)}
      <div class="sb-grid"><label class="sb-wide">Billing address (optional)<textarea maxlength="1000" name="billing_address" rows="2">${esc(order.billing_address)}</textarea></label>
      ${s.input("delivery_name","Delivery recipient",order.delivery.name,'maxlength="160"')}
      <label class="sb-wide">UK delivery address, including postcode<textarea name="delivery_address" maxlength="1000" rows="3">${esc(order.delivery.address)}</textarea></label></div>
      <p class="sb-error" role="alert"></p><div class="sb-actions"><button type="button" class="sb-secondary" data-sb-close>Cancel</button>
      <button class="sb-primary" type="submit">Save details</button></div></form>`;
    document.body.append(dialog);
    const form=dialog.querySelector("form"), read=name=>s.val(form,name), submit=form.querySelector('button[type="submit"]');
    dialog.querySelector("[data-sb-close]").onclick=()=>dialog.close();
    dialog.addEventListener("close",()=>dialog.remove(),{once:true});
    dialog.addEventListener("cancel",event=>{if(submit.disabled)event.preventDefault();});
    s.wire(form);
    const printing=order.stage==="sent_to_print";
    if(printing)form.querySelectorAll("form > .sb-grid:first-child :is(input,select,textarea),[data-sb-children] :is(input,select,textarea,button),[data-sb-add]").forEach(el=>el.disabled=true);
    form.onsubmit=async event=>{
      event.preventDefault();submit.disabled=true;dialog.querySelector("[data-sb-close]").disabled=true;
      try{
        await api(`/api/storybooks/${order.id}`,{method:"PATCH",body:JSON.stringify({
          details:s.details(form),buyer_name:read("buyer_name"),buyer_email:read("buyer_email"),billing_address:read("billing_address"),
          delivery_name:read("delivery_name"),delivery_address:read("delivery_address")
        })});
        dialog.close();toast("Storybook details saved");await reload();
      }catch(error){form.querySelector(".sb-error").textContent=error.message;}
      finally{submit.disabled=false;dialog.querySelector("[data-sb-close]").disabled=false;}
    };
    dialog.showModal();
  }
  function invoice(order,reload) {
    const theme=order.details.theme||"wedding";
    const pricing=theme==="wedding" ? `${order.quantity} × £34.99 = <strong>${s.price.format(order.quantity*34.99)}</strong> including UK delivery.` : `${order.quantity} copies · enter the agreed price per book, including UK delivery.`;
    showModal("Create storybook invoice",`<p class="full"><strong>${esc(s.themes[theme])}</strong><br>${pricing}<br>Bill to: ${esc(order.buyer_name)} · ${esc(order.buyer_email)}</p>
      ${theme==="wedding"?"":`<label class="full">Agreed price per book (£)<input id="sb-unit-price" type="number" min="0.01" max="10000" step="0.01" required></label>`}
      <label class="full">Payment due date<input id="sb-invoice-due" type="date" min="${today()}" value="${today()}" required></label>
      <label class="full"><span><input type="checkbox" required> I’ve confirmed the details and timing with the buyer.</span></label>`,
      async()=>{const i=await api(`/api/storybooks/${order.id}/invoice`,{method:"POST",body:JSON.stringify({due_date:value("#sb-invoice-due"),unit_price:document.querySelector("#sb-unit-price")?.value||null})});closeModal();toast(`Invoice ${i.number} created`);await reload();},
      "Confirm the details and timing with the buyer first. This creates the invoice without emailing it.");
  }
  function downloadBrief(order) {
    const d=order.details, theme=d.theme||"wedding";
    const lines=["# Storybook design brief","", "Story: "+s.themes[theme]];
    if(s.isWedding(theme))lines.push("Wedding date: "+date(d.wedding_date),"Venue: "+d.venue,
      ...(d.reception?["Reception: "+d.reception]:[]));
    if(d.destination)lines.push("Holiday destination: "+d.destination);
    d.books.forEach((b,i)=>lines.push("", "## Book "+(i+1),"Child’s name: "+b.name,
      ...(b.role==="child"?[]:["Wedding role: "+s.role[b.role]]),
      "Hair: "+(b.hair_other||s.hair[b.hair]),"Identical copies: "+b.quantity,
      "Dedication: "+(b.dedication||"(none supplied)")));
    lines.push("","Use the chosen story design. Prepare separate interior and hardback cover proofs for review.");
    const url=URL.createObjectURL(new Blob([lines.join("\n")],{type:"text/markdown;charset=utf-8"}));
    const link=document.createElement("a");link.href=url;link.download="storybook-"+order.id+"-design-brief.md";
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function renderOrders(host, orders, reload) {
    host.innerHTML=orders.map(order=>{
      const d=order.details,i=order.invoice,live=i&&!["void","cancelled"].includes(i.status);
      const closed=["cancelled","dispatched"].includes(order.stage);
      return `<article class="sb-card" data-sb-id="${order.id}"><h3>${esc(order.buyer_name)}</h3>
      <p><span class="sb-status">${esc(s.statuses[order.stage])}</span> · ${order.quantity} book(s) · <strong>${order.total===null?"Price to confirm":s.price.format(order.total)}</strong></p>
      <p><a href="mailto:${esc(order.buyer_email)}">${esc(order.buyer_email)}</a> · ${d.gift?"Gift order · ":""}${order.wedding_id?"Linked wedding booking":"Standalone request"}</p>
      <p><strong>${esc(s.themes[d.theme||"wedding"])}</strong></p>
      ${s.isWedding(d.theme||"wedding")?`<p>Wedding: ${date(d.wedding_date)} · ${esc(d.venue)}${d.reception?" / "+esc(d.reception):""} · ${esc(s.ceremony[d.ceremony])}</p>`:d.destination?`<p>Holiday destination: ${esc(d.destination)}</p>`:""}
      <p>Requested by: ${date(d.needed_by)}</p>
      <details><summary>Personalisation and delivery</summary><ul>${d.books.map(b=>`<li><strong>${esc(b.name)}</strong>${b.role==="child"?"":" · "+esc(s.role[b.role])} · ${esc(b.hair_other||s.hair[b.hair])} · ${b.quantity} copies${b.dedication?"<br>Dedication: "+esc(b.dedication):""}</li>`).join("")}</ul>
      <p>Bill to: ${esc(order.buyer_name)}${order.billing_address?" · "+esc(order.billing_address):""}</p><p>Deliver to: ${esc(order.delivery.name||"To confirm")}${order.delivery.address?" · "+esc(order.delivery.address):""}</p></details>
      ${live?`<p>Invoice ${esc(i.number)} · ${s.price.format(i.paid)} paid · ${s.price.format(i.balance)} outstanding</p>`:""}
      <div class="sb-actions">
      ${!closed?`<button class="sb-secondary" type="button" data-sb-act="edit">Review &amp; edit</button>`:""}
      ${!closed&&!live?`<button class="sb-primary" type="button" data-sb-act="invoice">Create invoice</button><button class="sb-secondary" type="button" data-sb-act="cancelled">Cancel request</button>`:""}
      ${live?`<a class="sb-secondary" href="/api/invoices/${i.id}/pdf">Invoice PDF</a><button class="sb-secondary" type="button" data-sb-act="email">Email invoice</button>
      ${i.balance>0?`<button class="sb-primary" type="button" data-sb-act="payment">Record payment</button>`:`<a class="sb-secondary" href="/api/invoices/${i.id}/receipt.pdf">Receipt PDF</a>`}`:""}
      ${live&&i.balance<=0&&order.stage!=="cancelled"?`<button class="sb-secondary" type="button" data-sb-act="brief">Download design brief</button>`:""}
      ${order.stage==="paid"?`<button class="sb-primary" type="button" data-sb-act="sent_to_print">Mark sent to print</button>`:""}
      ${order.stage==="sent_to_print"?`<button class="sb-primary" type="button" data-sb-act="dispatched">Mark dispatched</button>`:""}
      </div></article>`;
    }).join("")||"<p>No storybook requests yet.</p>";
    host.querySelectorAll("[data-sb-act]").forEach(button=>button.onclick=()=>run(async()=>{
      const order=orders.find(row=>row.id===button.closest("[data-sb-id]").dataset.sbId);
      const action=button.dataset.sbAct;
      if(action==="brief")return downloadBrief(order);
      if(action==="edit")return edit(order,reload);
      if(action==="invoice")return invoice(order,reload);
      if(action==="email")return emailInvoice(order.invoice.id);
      if(action==="payment")return payment(order,reload);
      if(action==="cancelled"&&!confirm("Cancel this storybook request?"))return;
      await api(`/api/storybooks/${order.id}/fulfilment`,{method:"POST",body:JSON.stringify({stage:action})});
      await reload();
    },button));
  }
  async function overview() {
    const host=document.querySelector("#content");
    host.innerHTML='<section class="panel sb-admin-list"><h2>Storybooks</h2><p>Review requests, invoice the buyer and track each book from payment to dispatch.</p><p><a href="/storybook-order" target="_blank" rel="noopener">Open the public order form</a></p><div data-sb-orders>Loading requests…</div><div class="sb-actions" data-sb-pages></div></section>';
    const list=host.querySelector("[data-sb-orders]");
    try{
      const orders=await api(`/api/storybooks?offset=${page*50}`);
      if(!list.isConnected)return;
      renderOrders(list,orders.slice(0,50),overview);
      const pages=host.querySelector("[data-sb-pages]");
      if(page>0)pages.insertAdjacentHTML("beforeend",'<button class="sb-secondary" data-sb-prev>Previous 50</button>');
      if(orders.length>50)pages.insertAdjacentHTML("beforeend",'<button class="sb-secondary" data-sb-next>Next 50</button>');
      if(pages.querySelector("[data-sb-prev]"))pages.querySelector("[data-sb-prev]").onclick=()=>{page--;overview();};
      if(pages.querySelector("[data-sb-next]"))pages.querySelector("[data-sb-next]").onclick=()=>{page++;overview();};
    }catch(error){if(list.isConnected)list.textContent=error.message;}
  }
  const oldRender=render;
  render=function(...args){
    if(state.view==="storybooks"){
      document.querySelector("#page-eyebrow").textContent="WEDDINGS BY MARK";
      document.querySelector("#page-title").textContent="Storybooks";
      document.querySelector("#page-subtitle").textContent="Requests, payments and orders";
      overview();
      return;
    }
    return oldRender.apply(this,args);
  };
  const oldBookingOverview=renderOverview;
  renderOverview=function(r,body,...args){
    const result=oldBookingOverview.call(this,r,body,...args);
    if(r.brand!=="wbm"||r.kind!=="wedding")return result;
    const marker=document.createElement("div");
    body.append(marker);
    const load=async()=>{
      try{
        const orders=await api(`/api/storybooks?wedding_id=${encodeURIComponent(r.id)}`);
        if(!marker.isConnected||!orders.length)return;
        marker.className="panel sb-admin-list";
        marker.innerHTML='<h3>Storybook requests for this booking</h3><div></div>';
        renderOrders(marker.lastElementChild,orders.slice(0,50),load);
      }catch(error){if(marker.isConnected)marker.textContent=error.message;}
    };
    load();
    return result;
  };
})();
