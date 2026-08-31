/* V8.21 — complete Final Wedding Timings record, PDF and submission status. */
(() => {
  "use strict";
  const baseRenderTabV820 = renderTab;
  const baseRecordNextActionV820 = recordNextAction;

  recordNextAction=function(r,portal){
    const review=(r.tasks||[]).find(task=>task.workflow_key==="wbm_review_final_timings"&&!task.completed);
    if(review)return {title:"Review the couple’s final wedding timings",detail:"Their completed run sheet is ready. Check the coverage and preparation travel before the final call.",tab:"Journey",label:"Review timings"};
    return baseRecordNextActionV820(r,portal);
  };

  function durationText(value) {
    const minutes=Math.max(0,Number(value||0)),hours=Math.floor(minutes/60),remainder=minutes%60;
    return [hours?`${hours} hr${hours===1?"":"s"}`:"",remainder?`${remainder} min`:""].filter(Boolean).join(" ")||"0 min";
  }
  function answer(data,key,fallback="Not supplied") {
    const value=data?.[key];
    if(value===true)return "Yes";if(value===false)return "No";
    return value===null||value===undefined||String(value).trim()===""?fallback:String(value);
  }
  function dateAfterStudioNinjaCutoff(value) { return Boolean(value && value > "2026-10-20"); }

  const finalTimingsLabels={ceremony_time:"Ceremony time",ceremony_duration:"Ceremony duration (minutes)",ceremony_venue:"Ceremony venue and address",reception_same:"Reception at the same venue",reception_venue:"Reception venue and address",prep_photos:"Preparation photographs",prep_person:"Who is getting ready",prep_venue:"Preparation venue and address",travel_minutes:"Travel to ceremony (minutes)",start_choice:"Preferred photography start",requested_start:"Requested earlier start",prep_notes:"Preparation notes",second_prep:"Second preparation location",group_photo_time:"Group photograph time",meal_time:"Wedding breakfast / meal time",speeches_time:"Speeches time",speeches_position:"Speeches position",evening_time:"Evening guests arrive",cake_time:"Cake cutting",first_dance_time:"First dance",later_event:"Essential event after first dance",later_event_name:"Later event",later_event_time:"Later event time",extra_stops:"Additional stops or venues",day_contact:"Wedding-day contact",day_mobile:"Wedding-day mobile",coordinator:"Venue coordinator",group_count:"Formal group photographs",important_notes:"Important details and requests"};

  function showCompleteFinalTimings(r,submission){
    const values=submission.data||{},content=document.querySelector("#modal-content"),modal=document.querySelector("#modal");
    const rows=Object.entries(finalTimingsLabels).map(([key,label])=>`<div><dt>${esc(label)}</dt><dd>${esc(answer(values,key)).replace(/\n/g,"<br>")}</dd></div>`).join("");
    modal.classList.remove("pdf-preview-modal");
    content.innerHTML=`<div class="modal-head"><div><small>COMPLETE CLIENT SUBMISSION</small><h2>Final Wedding Timings</h2><p>${esc(r.title)} · submitted ${esc(fmtDateTime(submission.submitted_at))}</p></div><button type="button" id="close-modal">×</button></div><div class="v821-answer-modal"><dl>${rows}</dl><footer><span>This is the complete form submitted by the couple.</span><button class="primary" id="close-final-answers" type="button">Close</button></footer></div>`;
    modal.classList.remove("hidden");document.querySelector("#modal-overlay").classList.remove("hidden");
    document.querySelector("#close-modal").onclick=document.querySelector("#close-final-answers").onclick=closeModal;
  }

  window.openFinalTimingsRecord=async function(r){
    const portal=state.currentPortal||{},submission=(portal.submissions||[]).find(item=>item.form_type==="final_timings");
    if(submission){showCompleteFinalTimings(r,submission);return}
    await selectRecordTab(r,"Journey",true);
    let attempts=0;
    const reveal=()=>{
      const panel=document.querySelector("#drawer .v820-final");
      if(panel){panel.scrollIntoView({behavior:"smooth",block:"start"});return}
      attempts+=1;
      if(attempts<20)setTimeout(reveal,75);
      else toast("Final Wedding Timings has not been submitted yet");
    };
    reveal();
  };

  function waitingPanel(r, portal) {
    const isLegacy=r.legacy_source==="studio_ninja",eligible=isLegacy&&dateAfterStudioNinjaCutoff(r.event_date),available=Boolean(portal.final_timings?.available);
    const safety=isLegacy
      ? eligible
        ? '<div class="v820-safety"><strong>Studio Ninja safety rule</strong><span>This Final Wedding Timings invitation is the one permitted automatic email. It sends 30 days before this wedding. Every other automatic Studio Ninja email remains blocked.</span></div>'
        : '<div class="v820-safety manual"><strong>Studio Ninja — manual only</strong><span>This wedding is not after 20 October 2026, so no automatic email will be sent. You can still open the form and deliberately send the link yourself.</span></div>'
      : '<p>The 30-day check-in opens this form and sends the couple directly to it. Your edited email template remains in use.</p>';
    return `<section class="v820-waiting"><div><small>STEP 4 · WEDDING-DAY RUN SHEET</small><h3>Final Wedding Timings</h3><p>${available?"The form is open and waiting for the couple to submit it.":"It opens automatically 30 days before the wedding. You can open it earlier when needed."}</p></div><span class="v820-state ${available?"scheduled":"scheduled"}">${available?"Not submitted yet":"Not open yet"}</span>${safety}<div class="v820-actions">${available?'<button class="primary" data-send-final-timings type="button">Send timings form now</button>':'<button class="secondary" data-open-final-timings type="button">Open without emailing</button><button class="primary" data-open-send-final-timings type="button">Open & send form now</button>'}</div></section>`;
  }

  function submittedPanel(r, portal, submission) {
    const values=submission.data||{},calc=values._calculation||{},reviewed=portal.final_timings?.reviewed_at;
    const status=calc.status==="over"?`Over by ${durationText(calc.over_standard_minutes)}`:calc.status==="within_grace"?"Within 15-minute grace":calc.status==="package_review"?"Package needs checking":"Fits included coverage";
    const timeline=(calc.timeline||[]).map(item=>`<div><b>${esc(item.time)}</b><span><strong>${esc(item.event)}</strong><small>${esc(item.detail||"")}</small></span></div>`).join("");
    const changed=submission.submission_source==="client_portal_updated"?` · UPDATED ${esc(fmtDateTime(submission.updated_at))}`:"";
    return `<section class="v820-submitted"><div class="v821-submission-proof"><i>✓</i><span><small>FORM SUBMITTED</small><strong>${esc(fmtDateTime(submission.submitted_at))}</strong>${changed?`<em>${changed.replace(" · ","")}</em>`:""}</span></div><header><div><small>FINAL WEDDING TIMINGS · COMPLETE</small><h3>Your working run sheet</h3></div><span class="v820-state ${calc.coverage_warning?"warning":"ready"}">${esc(status)}</span></header>
      <div class="v820-coverage"><article><small>SUGGESTED START</small><strong>${esc(calc.suggested_start||"Check")}</strong></article><article><small>EXPECTED FINISH</small><strong>${esc(calc.expected_finish||"Check")}</strong></article><article><small>EXPECTED COVERAGE</small><strong>${durationText(calc.coverage_minutes)}</strong></article><article><small>PACKAGE ALLOWANCE</small><strong>${calc.package_allowance_minutes==null?"Check package":durationText(calc.package_allowance_minutes)}</strong></article></div>
      ${calc.coverage_warning?`<div class="v820-alert"><strong>Coverage warning</strong><span>These timings exceed the included coverage by ${durationText(calc.over_standard_minutes)}. The form suggests ${calc.additional_hours_suggested} extra hour${calc.additional_hours_suggested===1?"":"s"}, but nothing has been charged or changed.</span></div>`:""}
      ${calc.travel_warning?`<div class="v820-alert private"><strong>Private preparation/travel check</strong><span>Only ${durationText(calc.prep_window_minutes)} remains for preparation photographs before leaving at ${esc(calc.prep_departure)} to arrive 15 minutes before the ceremony. This warning is shown to you, not the couple.</span></div>`:""}
      ${calc.earlier_start_minutes?`<div class="v820-note"><strong>Spare coverage used sensibly</strong><span>The suggested start is ${durationText(calc.earlier_start_minutes)} earlier, using spare included time without creating an overrun.</span></div>`:""}
      <div class="v820-grid"><section><h4>Run sheet</h4><div class="v820-timeline">${timeline||"No timeline calculated"}</div></section><section><h4>Contacts & notes</h4><dl><dt>Day contact</dt><dd>${esc(answer(values,"day_contact"))} · ${esc(answer(values,"day_mobile"))}</dd><dt>Coordinator</dt><dd>${esc(answer(values,"coordinator"))}</dd><dt>Formal groups</dt><dd>${esc(answer(values,"group_count"))}</dd><dt>Extra stops</dt><dd>${esc(answer(values,"extra_stops"))}</dd><dt>Important details</dt><dd>${esc(answer(values,"important_notes"))}</dd><dt>Preparation notes</dt><dd>${esc(answer(values,"prep_notes"))}</dd></dl></section></div>
      <div class="v821-record-actions"><button class="secondary" data-view-final-timings type="button">View complete form</button><button class="primary" data-preview-final-timings type="button">View / download PDF</button><span>A PDF copy is retained automatically in Files.</span></div>
      <footer>${reviewed?`<span class="v820-reviewed">✓ Reviewed ${esc(fmtDateTime(reviewed))}</span>`:'<button class="primary" data-review-final-timings type="button">I’ve reviewed these timings</button>'}<span>Couple updates reopen your private review task.</span></footer></section>`;
  }

  function appendFinalTimings(r, body) {
    if(r.kind!=="wedding")return;
    const portal=state.currentPortal||{},submission=(portal.submissions||[]).find(item=>item.form_type==="final_timings");
    const host=body.querySelector(".v811-journey");
    if(!host)return;
    host.querySelectorAll(".v820-final").forEach(section=>section.remove());
    host.insertAdjacentHTML("beforeend",`<section class="v811-journey-block v820-final"><header><div><small>STEP 4</small><h3>Final wedding timings</h3></div><span>Coverage check and private run sheet</span></header><div>${submission?submittedPanel(r,portal,submission):waitingPanel(r,portal)}</div></section>`);
    const open=body.querySelector("[data-open-final-timings]");
    if(open)open.onclick=async()=>{if(!confirm("Open the Final Wedding Timings Form early for this couple?"))return;try{await api(`/api/bookings/${r.id}/final-details`,{method:"POST",body:JSON.stringify({unlocked:true,reason:"Opened early from the Final Wedding Timings panel"})});toast("Final Wedding Timings Form opened");await refresh();openDrawer(r.id,"Journey")}catch(error){toast(error.message,"error")}};
    const send=body.querySelector("[data-send-final-timings]");
    const openAndSend=body.querySelector("[data-open-send-final-timings]");
    const sendNow=async(button,openFirst=false)=>{
      const imported=r.legacy_source==="studio_ninja";
      const warning=imported
        ? `Send the Final Wedding Timings Form to ${r.client.email} now?\n\nThis is one deliberate manual email. Every other Studio Ninja automatic email remains blocked.`
        : `Send the Final Wedding Timings Form to ${r.client.email} now?`;
      if(!confirm(warning))return;
      button.disabled=true;button.textContent="Sending…";
      try{
        if(openFirst)await api(`/api/bookings/${r.id}/final-details`,{method:"POST",body:JSON.stringify({unlocked:true,reason:"Opened early to send the Final Wedding Timings Form"})});
        await api(`/api/bookings/${r.id}/emails/send`,{method:"POST",body:JSON.stringify({template_key:"check_in_30",manual_confirmation:imported?"SEND ONE MANUAL EMAIL":null,manual_reason:imported?"Final Wedding Timings Form deliberately sent early":null})});
        toast("Final Wedding Timings Form emailed successfully");await refresh();openDrawer(r.id,"Journey");
      }catch(error){button.disabled=false;button.textContent=openFirst?"Open & send form now":"Send timings form now";toast(error.message,"error")}
    };
    if(send)send.onclick=()=>sendNow(send,false);
    if(openAndSend)openAndSend.onclick=()=>sendNow(openAndSend,true);
    const complete=body.querySelector("[data-view-final-timings]");
    if(complete&&submission)complete.onclick=()=>showCompleteFinalTimings(r,submission);
    const preview=body.querySelector("[data-preview-final-timings]");
    if(preview)preview.onclick=()=>showPdfPreview(`Final Wedding Timings — ${r.title}`,`/api/bookings/${r.id}/final-timings.pdf?inline=true`,`/api/bookings/${r.id}/final-timings.pdf`);
    const review=body.querySelector("[data-review-final-timings]");
    if(review)review.onclick=async()=>{try{await api(`/api/bookings/${r.id}/final-timings/review`,{method:"POST"});toast("Final wedding timings marked as reviewed");await refresh();openDrawer(r.id,"Journey")}catch(error){toast(error.message,"error")}};
  }

  renderTab=async function(r,tab,target=null){await baseRenderTabV820(r,tab,target);if(tab==="Journey"||tab==="Quote")appendFinalTimings(r,target||document.querySelector("#drawer-body"))};
})();
