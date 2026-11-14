(() => {
  "use strict";
  const s=window.WBMStorybooks;
  const allowed=()=>data?.storybooks_available;
  const card=()=>`<section class="sb-card" data-storybook-extra><h3>Personalised wedding storybook</h3>
    <p>Give your flower girl or pageboy a hardback story with their name on the cover, your wedding date and venue inside, and a little thank-you from you.</p>
    <p><strong>£34.99 per book including UK delivery.</strong></p>
    <p class="sb-actions"><a href="${s.sample}" target="_blank" rel="noopener">See a sample</a>
      <button type="button" class="sb-primary" data-sb-open ${quotePreview?"disabled":""}>Add a storybook</button></p>
    <div data-sb-requests></div></section>`;
  async function requests(target) {
    if (quotePreview || !target) return;
    try {
      const items=await api(`/api/client/${encodeURIComponent(token)}/storybooks`);
      if(!target.isConnected)return;
      target.innerHTML=items.map(item=>{
        const base=`/api/client/${encodeURIComponent(token)}/storybooks/invoices/${encodeURIComponent(item.invoice_id)}`;
        return `<p>${Number(item.quantity)} book(s) · ${s.esc(s.statuses[item.stage]||item.stage)}
          ${item.invoice_id?` · <a href="${base}/invoice.pdf">Invoice PDF</a>`:""}
          ${item.invoice_id && item.paid>0?` · <a href="${base}/receipt.pdf">Receipt PDF</a>`:""}</p>`;
      }).join("");
    } catch { if(target.isConnected) target.textContent="Could not load your storybook requests."; }
  }
  function openCard(host) {
    if (quotePreview || !allowed()) return;
    const dialog=document.createElement("dialog");
    dialog.className="sb-dialog";
    dialog.setAttribute("aria-labelledby","storybook-dialog-title");
    const venue=data.record.venue_or_project||"";
    const details={wedding_date:data.record.event_date,venue,ceremony:venue?"one_venue":""};
    dialog.innerHTML=`<h2 id="storybook-dialog-title">Add a storybook</h2><p>£34.99 per book including UK delivery. This is a request. Mark will confirm the details before invoicing. Any wedding details you change here apply to the book only.</p>
      <form>${s.fields(details)}${s.consent}<p class="sb-error" role="alert" data-sb-error></p>
      <div class="sb-actions"><button type="button" class="sb-secondary" data-sb-close>Close</button><button type="submit" class="sb-primary">Send storybook order request</button></div></form>`;
    document.body.append(dialog);
    const close=()=>dialog.close();
    dialog.querySelector("[data-sb-close]").onclick=close;
    dialog.addEventListener("cancel",event=>{if(dialog.querySelector('button[type="submit"]:disabled'))event.preventDefault();});
    dialog.addEventListener("close",()=>dialog.remove(),{once:true});
    const form=dialog.querySelector("form");
    const closeButton=dialog.querySelector("[data-sb-close]");
    const submitButton=form.querySelector('button[type="submit"]');
    const watch=new MutationObserver(()=>{closeButton.disabled=submitButton.disabled;});
    watch.observe(submitButton,{attributes:true,attributeFilter:["disabled"]});
    dialog.addEventListener("close",()=>watch.disconnect(),{once:true});
    s.requestForm(form,`/api/client/${encodeURIComponent(token)}/storybooks`,{onSuccess:()=>{
      dialog.innerHTML=`<h2 id="storybook-dialog-title" tabindex="-1">Thank you</h2><p>${s.esc(s.success)}</p><button type="button" class="sb-primary">Close</button>`;
      dialog.querySelector("button").onclick=close;
      dialog.querySelector("h2").focus();
      requests(host.querySelector("[data-sb-requests]"));
    }});
    dialog.showModal();
  }
  function prepend(host,label=false) {
    if(!allowed()||!host||host.querySelector("[data-storybook-extra]"))return;
    host.insertAdjacentHTML("afterbegin",(label?'<h2 class="sb-extras-heading">Extras</h2>':"")+card());
    host.querySelector("[data-sb-open]").onclick=()=>openCard(host);
    requests(host.querySelector("[data-sb-requests]"));
  }
  const oldAddons=renderAddons;
  renderAddons=function(...args){
    const before=document.querySelector("#addon-list [data-storybook-extra]");
    const result=oldAddons.apply(this,args);
    const host=document.querySelector("#addon-list");
    if(before&&host)host.prepend(before);else prepend(host);
    return result;
  };
  const oldQuote=quotePanel;
  quotePanel=function(...args){
    const result=oldQuote.apply(this,args);
    if(!document.querySelector("#addon-list"))prepend(document.querySelector("#panel"),true);
    return result;
  };
  const oldOverview=overview;
  overview=function(...args){
    const result=oldOverview.apply(this,args);
    prepend(document.querySelector("#panel"),true);
    return result;
  };
})();
