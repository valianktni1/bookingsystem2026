/* V8.20 — Final Wedding Timings Form and live coverage guidance. */
(() => {
  "use strict";

  requestedTabs.timings = "Final timings";
  if (requestedTab === "timings") active = "Final timings";

  const baseCompleted = completed;
  const baseTabDefinition = tabDefinition;
  const baseRender = render;
  const baseOverview = overview;
  let timingsStep = 0;

  completed = function () {
    return {...baseCompleted(), timings:Boolean(data?.final_timings?.submitted)};
  };

  tabDefinition = function () {
    const tabs = baseTabDefinition();
    if (data?.record?.kind === "wedding" && (data.final_timings?.available || data.final_timings?.submitted)) {
      const agreementIndex = tabs.findIndex(item => item.name === "Agreement");
      const timingTab = {name:"Final timings", icon:"◷", done:Boolean(data.final_timings?.submitted)};
      if (agreementIndex >= 0) tabs.splice(agreementIndex + 1, 0, timingTab);
      else tabs.push(timingTab);
    }
    return tabs;
  };

  overview = function () {
    baseOverview();
    if (data?.record?.kind !== "wedding") return;
    const available = Boolean(data.final_timings?.available);
    const submitted = Boolean(data.final_timings?.submitted);
    const journey = document.querySelector(".journey");
    if (!journey) return;
    journey.insertAdjacentHTML("beforeend", `<button class="${submitted?"done":""} ${available?"":"locked"}" data-final-timings-go ${available?"":"aria-disabled=\"true\""}><i>${submitted?"✓":available?"4":"🔒"}</i><span><strong>Final wedding timings</strong><small>${submitted?"Completed — you can still update it":available?"Ready for you":"Opens 30 days before your wedding"}</small></span></button>`);
    const button = document.querySelector("[data-final-timings-go]");
    button.onclick = () => available ? setActive("Final timings") : toast("This form opens 30 days before your wedding");
  };

  render = function () {
    if (active === "Final timings") finalTimingsForm();
    else baseRender();
  };

  function timeInput(label,name,value="",required=false,full=false) {
    return `<label class="${full?"full":""}">${label}${required?" *":""}<input type="time" name="${name}" value="${esc(value||"").slice(0,5)}" ${required?"required":""}></label>`;
  }
  function textInput(label,name,value="",required=false,full=false,type="text") {
    return `<label class="${full?"full":""}">${label}${required?" *":""}<input type="${type}" name="${name}" value="${esc(value||"")}" ${required?"required":""}></label>`;
  }
  function textArea(label,name,value="",placeholder="") {
    return `<label class="full">${label}<textarea name="${name}" rows="4" placeholder="${esc(placeholder)}">${esc(value||"")}</textarea></label>`;
  }
  function selectInput(label,name,options,value,required=false,full=false) {
    return `<label class="${full?"full":""}">${label}${required?" *":""}<select name="${name}" ${required?"required":""}>${options.map(([key,text])=>`<option value="${esc(key)}" ${String(value)===String(key)?"selected":""}>${esc(text)}</option>`).join("")}</select></label>`;
  }
  function yesNo(label,name,value,full=false) {
    const selected = value === true || value === "yes" ? "yes" : "no";
    return selectInput(label,name,[["yes","Yes"],["no","No"]],selected,true,full);
  }
  function minutesToText(value) {
    const minutes = Math.max(0,Number(value||0)), hours=Math.floor(minutes/60), remainder=minutes%60;
    return [hours?`${hours} hr${hours===1?"":"s"}`:"",remainder?`${remainder} min`:""].filter(Boolean).join(" ")||"0 min";
  }
  function toMinutes(value) {
    if (!value || !/^\d{2}:\d{2}/.test(value)) return null;
    const [hour,minute]=value.slice(0,5).split(":").map(Number); return hour*60+minute;
  }
  function clock(value) {
    const normal=((value%1440)+1440)%1440; return `${String(Math.floor(normal/60)).padStart(2,"0")}:${String(normal%60).padStart(2,"0")}`;
  }
  function after(value,reference) { return value < reference ? value+1440 : value; }

  function formValues(form) {
    const values={};
    for (const [key,value] of new FormData(form).entries()) values[key]=String(value).trim();
    for (const key of ["reception_same","prep_photos","later_event"]) values[key]=values[key]==="yes";
    values.ceremony_duration=Number(values.ceremony_duration||45);
    values.travel_minutes=Number(values.travel_minutes||0);
    return values;
  }

  function clientCalculation(values) {
    const ceremony=toMinutes(values.ceremony_time),dance=toMinutes(values.first_dance_time);
    if (ceremony===null||dance===null) return null;
    const normalStart=ceremony-60, finish=Math.max(after(dance,normalStart),values.later_event&&toMinutes(values.later_event_time)!==null?after(toMinutes(values.later_event_time),normalStart):dance);
    const included=data.final_timings?.coverage?.allowance_minutes;
    const base=Math.max(0,finish-normalStart),spare=included==null?0:Math.max(0,included-base);
    const requested=toMinutes(values.requested_start);
    const earlierBy=values.start_choice!=="earlier"&&values.prep_photos&&Number(values.travel_minutes)>0?Math.min(spare,60):0;
    const start=values.start_choice==="earlier"&&requested!==null?Math.min(requested,normalStart):normalStart-earlierBy;
    const coverage=Math.max(0,finish-start),over=included==null?null:Math.max(0,coverage-included);
    return {start,finish,coverage,included,over,flagged:included!=null&&coverage>included+15,withinGrace:included!=null&&coverage>included&&coverage<=included+15,earlierBy};
  }

  function updateTimingsPreview() {
    const form=document.querySelector("#final-timings-form"),host=document.querySelector("#timings-preview");
    if (!form||!host) return;
    const result=clientCalculation(formValues(form));
    if (!result) { host.innerHTML="<p>Add the ceremony and first-dance times to see the coverage check.</p>"; return; }
    let status="",css="ok";
    if (result.included==null) status="I will check these timings against your agreed package before our final call.";
    else if (result.flagged) { css="warning"; status=`These timings are ${minutesToText(result.over)} beyond the included coverage. You may need ${Math.ceil(result.over/60)} extra hour${Math.ceil(result.over/60)===1?"":"s"}; I will confirm this with you before anything changes.`; }
    else if (result.withinGrace) status="These timings are within the 15-minute grace period. No extra hour is suggested.";
    else status=`These timings fit within your ${minutesToText(result.included)} package coverage.`;
    host.className=`timings-preview ${css}`;
    host.innerHTML=`<small>LIVE COVERAGE CHECK</small><div><span><b>${clock(result.start)}</b> suggested start</span><span><b>${clock(result.finish)}</b> expected finish</span><span><b>${minutesToText(result.coverage)}</b> coverage</span></div><strong>${status}</strong>${result.earlierBy?`<p>I can use the spare ${minutesToText(result.earlierBy)} in your package to arrive earlier for preparations without creating an overrun.</p>`:""}`;
  }

  function finalTimingsForm() {
    if (!data.final_timings?.available && !data.final_timings?.submitted) {
      $("#panel").innerHTML='<div class="final-details-locked"><i>🔒</i><strong>Your Final Wedding Timings Form is not open yet</strong><span>It opens 30 days before your wedding, unless I open it earlier for you.</span></div>';
      return;
    }
    const x=existing("final_timings"),booking=existing("booking_form");
    const receptionDefault=x.reception_venue||booking.reception_details||data.record.venue_address||data.record.venue_or_project||"";
    $("#panel").innerHTML=`<div class="timings-heading"><small>YOUR WEDDING-DAY RUN SHEET</small><h2>Final Wedding Timings</h2><p>Complete the details below so I can prepare the day properly and check the expected photography coverage before our final telephone call.</p></div>${x._calculation?'<div class="complete">✓ Previously submitted — you can update it if anything changes.</div>':""}<form id="final-timings-form"><div class="form-progress timings-progress">${[1,2,3,4,5].map(()=>"<span></span>").join("")}</div>
      <section class="form-step" data-timing-step="0"><h3>1. Ceremony & reception</h3><p class="step-intro">Please confirm the key places and times.</p><div class="form-grid">${timeInput("Ceremony time","ceremony_time",x.ceremony_time||booking.ceremony_time,true)}${textInput("Expected ceremony length (minutes)","ceremony_duration",x.ceremony_duration||45,true,false,"number")}${textArea("Ceremony venue and full address *","ceremony_venue",x.ceremony_venue||booking.ceremony_details||data.record.venue_address||data.record.venue_or_project||"")}${yesNo("Is the reception at the same venue?","reception_same",x.reception_same)}<div data-reception-venue class="full">${textArea("Reception venue and full address","reception_venue",receptionDefault)}</div></div></section>
      <section class="form-step" data-timing-step="1"><h3>2. Preparations & travel</h3><p class="step-intro">I normally begin at least one hour before the ceremony. Spare included coverage may let me start earlier.</p><div class="form-grid">${yesNo("Would you like preparation photographs?","prep_photos",x.prep_photos??true)}<div data-prep-fields class="full form-grid nested-grid">${textInput("Who will I photograph getting ready?","prep_person",x.prep_person||"")}${textArea("Preparation venue and full address","prep_venue",x.prep_venue||"")}${textInput("Travel time from preparations to ceremony (minutes)","travel_minutes",x.travel_minutes||0,true,false,"number")}${selectInput("Preferred start","start_choice",[["normal","Use my recommended start"],["earlier","Request an earlier start"]],x.start_choice||"normal",true)}<div data-requested-start>${timeInput("Earlier start requested","requested_start",x.requested_start||"")}</div>${textArea("Preparation notes","prep_notes",x.prep_notes||"","Room details, access, parking or anything useful")}${textArea("Second preparation location or person","second_prep",x.second_prep||"")}</div></div></section>
      <section class="form-step" data-timing-step="2"><h3>3. Your running order</h3><p class="step-intro">Approximate times are absolutely fine.</p><div class="form-grid">${timeInput("Group photographs","group_photo_time",x.group_photo_time)}${timeInput("Wedding breakfast / meal","meal_time",x.meal_time)}${timeInput("Speeches","speeches_time",x.speeches_time)}${selectInput("When are the speeches?","speeches_position",[["Before the meal","Before the meal"],["Between courses","Between courses"],["After the meal","After the meal"]],x.speeches_position||"After the meal")}${timeInput("Evening guests arrive","evening_time",x.evening_time)}${timeInput("Cake cutting","cake_time",x.cake_time)}${timeInput("First dance","first_dance_time",x.first_dance_time,true)}${yesNo("Is there an essential photograph after the first dance?","later_event",x.later_event,true)}<div data-later-event class="full form-grid nested-grid">${textInput("What is the later event?","later_event_name",x.later_event_name||"")}${timeInput("Later event time","later_event_time",x.later_event_time)}</div>${textArea("Extra venues, stops or travel during the day","extra_stops",x.extra_stops||"")}</div></section>
      <section class="form-step" data-timing-step="3"><h3>4. Contacts & important details</h3><p class="step-intro">Please give me one reliable contact for the wedding day.</p><div class="form-grid">${textInput("Wedding-day contact name","day_contact",x.day_contact||data.record.client.first_name,true)}${textInput("Wedding-day mobile","day_mobile",x.day_mobile||data.record.client.phone||"",true,false,"tel")}${textInput("Coordinator / venue contact","coordinator",x.coordinator||"")}${selectInput("Approximate number of formal group photographs","group_count",[["None","None"],["1-5","1–5"],["6-10","6–10"],["More than 10","More than 10"]],x.group_count||"1-5",true)}${textArea("Important family details, surprises or anything I should know","important_notes",x.important_notes||"")}</div></section>
      <section class="form-step" data-timing-step="4"><h3>5. Check & send</h3><p class="step-intro">This is guidance only. Nothing is charged and no package is changed by this form.</p><div id="timings-preview" class="timings-preview"></div><label class="timings-confirm"><input type="checkbox" required><span>I have checked these timings and understand I can update them if plans change.</span></label></section>
      <div class="form-step-actions"><button id="timings-back" class="secondary-client" type="button">Back</button><button id="timings-next" class="primary" type="button">Continue</button><button id="timings-save" class="primary" type="submit">Send my final timings</button></div></form>`;

    const form=document.querySelector("#final-timings-form"),steps=[...form.querySelectorAll("[data-timing-step]")],bars=[...form.querySelectorAll(".timings-progress span")];
    form.elements.ceremony_venue.required=true;
    form.elements.ceremony_duration.min="10";form.elements.ceremony_duration.max="180";
    form.elements.travel_minutes.min="0";form.elements.travel_minutes.max="180";
    const conditional=()=>{
      const same=form.elements.reception_same.value==="yes",prep=form.elements.prep_photos.value==="yes",earlier=form.elements.start_choice.value==="earlier",later=form.elements.later_event.value==="yes";
      form.querySelector("[data-reception-venue]").classList.toggle("hidden",same);form.elements.reception_venue.required=!same;
      form.querySelector("[data-prep-fields]").classList.toggle("hidden",!prep);form.elements.prep_person.required=prep;form.elements.prep_venue.required=prep;
      form.querySelector("[data-requested-start]").classList.toggle("hidden",!earlier);form.elements.requested_start.required=earlier;
      form.querySelector("[data-later-event]").classList.toggle("hidden",!later);form.elements.later_event_name.required=later;form.elements.later_event_time.required=later;
      updateTimingsPreview();
    };
    const show=()=>{steps.forEach((step,index)=>step.classList.toggle("active",index===timingsStep));bars.forEach((bar,index)=>bar.className=index<timingsStep?"done":index===timingsStep?"active":"");$("#timings-back").classList.toggle("hidden",timingsStep===0);$("#timings-next").classList.toggle("hidden",timingsStep===steps.length-1);$("#timings-save").classList.toggle("hidden",timingsStep!==steps.length-1);conditional()};
    form.oninput=conditional;form.onchange=conditional;
    $("#timings-back").onclick=()=>{timingsStep=Math.max(0,timingsStep-1);show()};
    $("#timings-next").onclick=()=>{const invalid=[...steps[timingsStep].querySelectorAll("input,select,textarea")].find(input=>!input.closest(".hidden")&&!input.checkValidity());if(invalid){invalid.reportValidity();return}timingsStep=Math.min(steps.length-1,timingsStep+1);show();window.scrollTo({top:$("#panel").offsetTop-10,behavior:"smooth"})};
    form.onsubmit=async event=>{event.preventDefault();try{await api(`/api/client/${token}/forms`,{method:"POST",body:JSON.stringify({form_type:"final_timings",data:formValues(form)})});data=await api(`/api/client/${token}`);timingsStep=0;renderTabs();render();toast("Your final wedding timings have been sent safely")}catch(error){toast(error.message)}};
    show();
  }
})();
