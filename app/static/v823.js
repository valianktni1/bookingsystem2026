/* V8.23 — private complete final telephone-call pack. */
(() => {
  "use strict";
  const baseRenderTabV823 = renderTab;

  function readinessCard(data) {
    const readiness=data.readiness||{},warnings=readiness.warnings||[];
    const badges=[
      [readiness.booking_form,"Booking form"],
      [readiness.final_timings,"Final timings"],
      [readiness.agreement_complete,"Agreement"],
      [Number(readiness.outstanding||0)<=0,"Account"],
    ];
    return `<div class="v823-readiness"><div class="v823-badges">${badges.map(([ready,label])=>`<span class="${ready?"ready":"check"}"><i>${ready?"✓":"!"}</i>${esc(label)}</span>`).join("")}</div>${warnings.length?`<div class="v823-warnings"><strong>Check during the call</strong>${warnings.map(text=>`<span>• ${esc(text)}</span>`).join("")}</div>`:`<div class="v823-all-ready"><strong>✓ Everything recorded is ready for the call</strong></div>`}</div>`;
  }

  function panel(r,data) {
    const imported=r.legacy_source==="studio_ninja";
    return `<section class="v811-journey-block v823-final-call-pack"><header><div><small>STEP 5</small><h3>Complete final telephone-call pack</h3></div><span>Private checklist, notes and printable working copy</span></header><div class="v823-body">
      <div class="v823-proof ${data.completed?"complete":""}"><i>${data.completed?"✓":"☎"}</i><span><small>${data.completed?"FINAL CALL COMPLETED":"READY FOR YOUR FINAL CALL"}</small><strong>${data.completed?(data.completed_at?fmtDateTime(data.completed_at):"Task marked complete"):`${data.checked_count}/${data.checklist_count} checks confirmed`}</strong><em>${data.completed_by?`Completed by ${esc(data.completed_by)}`:"Save your progress and return whenever you need to."}</em></span></div>
      ${readinessCard(data)}
      ${imported?`<div class="v823-safety"><strong>Studio Ninja protection remains on</strong><span>This is your private working pack only. Saving it, printing it or completing the call sends no email and does not enable any other automation.</span></div>`:`<div class="v823-safety"><strong>Private working area</strong><span>Nothing here is shown or emailed to the couple. It simply brings the existing booking records together for your call.</span></div>`}
      <section class="v823-checklist"><div><small>FINAL-CALL CHECKLIST</small><h4>Work through these while you speak</h4></div>${(data.checklist||[]).map(item=>`<label><input type="checkbox" data-final-call-check="${attr(item.key)}" ${item.checked?"checked":""}><span><i>✓</i>${esc(item.label)}</span></label>`).join("")}</section>
      <label class="v823-notes"><span><small>PRIVATE CALL NOTES</small><strong>Anything agreed, changed or needing a follow-up</strong></span><textarea data-final-call-notes rows="7" placeholder="Type your notes here while you speak to the couple…">${esc(data.notes||"")}</textarea></label>
      <div class="v823-actions"><span>The PDF is refreshed and retained privately in Files whenever you save or open it.</span><button class="secondary" data-final-call-save type="button">Save progress</button><button class="secondary" data-final-call-pdf type="button">View / download complete pack</button>${data.completed?'<button class="secondary" data-final-call-reopen type="button">Reopen final call</button>':'<button class="primary" data-final-call-complete type="button">Mark final call complete</button>'}</div>
    </div></section>`;
  }

  function payload(body,completed) {
    const checklist={};
    body.querySelectorAll("[data-final-call-check]").forEach(input=>checklist[input.dataset.finalCallCheck]=input.checked);
    return {checklist,notes:body.querySelector("[data-final-call-notes]")?.value||"",completed};
  }

  async function savePack(r,body,completed,message) {
    const result=await api(`/api/bookings/${r.id}/final-call-pack`,{method:"PUT",body:JSON.stringify(payload(body,completed))});
    if(message)toast(message);
    await refresh();
    openDrawer(r.id,"Journey");
    return result;
  }

  function wire(r,body,data) {
    const save=body.querySelector("[data-final-call-save]");
    if(save)save.onclick=async()=>{save.disabled=true;try{await savePack(r,body,data.completed,"Final-call progress saved privately")}catch(error){save.disabled=false;toast(error.message,"error")}};
    const complete=body.querySelector("[data-final-call-complete]");
    if(complete)complete.onclick=async()=>{if(!confirm("Mark the final telephone call as complete?\n\nThis saves your private checklist and notes. It does not email the couple."))return;complete.disabled=true;try{await savePack(r,body,true,"Final telephone call completed")}catch(error){complete.disabled=false;toast(error.message,"error")}};
    const reopen=body.querySelector("[data-final-call-reopen]");
    if(reopen)reopen.onclick=async()=>{if(!confirm("Reopen this final call so it appears in your things to do again?"))return;reopen.disabled=true;try{await savePack(r,body,false,"Final telephone call reopened")}catch(error){reopen.disabled=false;toast(error.message,"error")}};
    const pdf=body.querySelector("[data-final-call-pdf]");
    if(pdf)pdf.onclick=async()=>{pdf.disabled=true;try{await api(`/api/bookings/${r.id}/final-call-pack`,{method:"PUT",body:JSON.stringify(payload(body,data.completed))});showPdfPreview(`Final Call Pack — ${r.title}`,`/api/bookings/${r.id}/final-call-pack.pdf?inline=true`,`/api/bookings/${r.id}/final-call-pack.pdf`)}catch(error){toast(error.message,"error")}finally{pdf.disabled=false}};
  }

  async function appendFinalCallPack(r,body) {
    if(r.kind!=="wedding")return;
    const host=body.querySelector(".v811-journey");
    if(!host)return;
    host.querySelectorAll(".v823-final-call-pack").forEach(section=>section.remove());
    const placeholder=document.createElement("section");
    placeholder.className="v811-journey-block v823-final-call-pack";
    placeholder.innerHTML='<div class="v823-loading">Preparing the private final-call pack…</div>';
    host.append(placeholder);
    try{
      const data=await api(`/api/bookings/${r.id}/final-call-pack`);
      if(!placeholder.isConnected)return;
      placeholder.outerHTML=panel(r,data);
      const rendered=host.querySelector(".v823-final-call-pack");
      if(rendered)wire(r,rendered,data);
    }catch(error){
      if(placeholder.isConnected)placeholder.innerHTML=`<div class="v823-error"><strong>Final-call pack could not be loaded</strong><span>${esc(error.message)}</span></div>`;
    }
  }

  renderTab=async function(r,tab,target=null){
    await baseRenderTabV823(r,tab,target);
    if(tab==="Journey")await appendFinalCallPack(r,target||document.querySelector("#drawer-body"));
  };
})();
