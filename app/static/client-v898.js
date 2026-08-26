/* V8.29 — server-driven form, payment plans, confirmation and durable draft recovery. */
(() => {
  const legacyBookingForm = bookingForm;
  const BOOKING_DRAFT_MAX_AGE = 30 * 24 * 60 * 60 * 1000;

  function bookingDraftKey() {
    return `wbm-booking-form-draft:${data?.record?.id || token}`;
  }

  function clearBookingDraft() {
    try { localStorage.removeItem(bookingDraftKey()); } catch (_) {}
  }

  function readBookingDraft() {
    try {
      const saved = JSON.parse(localStorage.getItem(bookingDraftKey()) || "null");
      const savedAt = Number(saved?.savedAt);
      if (!saved || !saved.values || typeof saved.values !== "object") return null;
      if (!Number.isFinite(savedAt) || Date.now() - savedAt > BOOKING_DRAFT_MAX_AGE) {
        clearBookingDraft();
        return null;
      }
      saved.savedAt = savedAt;
      return saved;
    } catch (_) { return null; }
  }

  function bookingDraftValues(form) {
    const values = {};
    for (const [key,value] of new FormData(form).entries()) values[key] = String(value).trim();
    form.querySelectorAll('input[type="checkbox"][name]').forEach(input => {
      if (!input.checked) values[input.name] = "";
    });
    return values;
  }

  function draftTime(savedAt) {
    return new Intl.DateTimeFormat("en-GB", {hour:"2-digit", minute:"2-digit"})
      .format(new Date(savedAt));
  }

  function writeBookingDraft(form) {
    try {
      const savedAt = Date.now();
      localStorage.setItem(bookingDraftKey(), JSON.stringify({
        step: bookingStep,
        savedAt,
        values: bookingDraftValues(form),
      }));
      const status = document.querySelector("#booking-draft-status");
      if (status) status.innerHTML = `<strong>✓ Saved on this device</strong><span>Last saved at ${draftTime(savedAt)}. You can safely return using this same device and browser.</span>`;
    } catch (_) { /* The form still submits when browser storage is unavailable. */ }
  }

  function wireBookingDraft(form) {
    const remember = () => writeBookingDraft(form);
    form.addEventListener("input", remember);
    form.addEventListener("change", remember);
    document.querySelector("#booking-back")?.addEventListener("click", remember);
    document.querySelector("#booking-next")?.addEventListener("click", remember);
  }

  function defaultValue(key, existing) {
    const defaults = {
      primary_full_name:`${data.record.client.first_name} ${data.record.client.last_name||""}`.trim(),
      primary_phone:data.record.client.phone||"", primary_email:data.record.client.email||"",
      partner_full_name:data.record.client.partner_name||"", street_address:data.record.client.address||"",
      wedding_date:data.record.event_date||"", ceremony_details:data.record.venue_address||data.record.venue_or_project||"",
      package_selected:data.record.package_name||"", payment_plan:"standard"
    };
    return existing[key] ?? defaults[key] ?? "";
  }

  function renderField(item, existing) {
    const value = defaultValue(item.key,existing), required=item.required?"required":"", star=item.required?" *":"", full=item.width==="full"?"full":"";
    const help=item.help_text?`<small class="field-help">${esc(item.help_text)}</small>`:"";
    if(item.field_type==="venue"){
      const venue=data.record.venue_or_project||"",address=data.record.venue_address||"";
      return `<input name="venue_name" type="hidden" value="${esc(venue)}"><input name="venue_address" type="hidden" value="${esc(address)}"><input name="venue_place_id" type="hidden" value="${esc(data.record.venue_place_id||"")}"><input name="venue_lat" type="hidden" value="${esc(data.record.venue_lat??"")}"><input name="venue_lng" type="hidden" value="${esc(data.record.venue_lng??"")}"><label class="full">${esc(item.label)}<input value="${esc(venue)}${address&&address!==venue?` - ${esc(address)}`:""}" readonly>${help}</label>`;
    }
    if(item.field_type==="package"){
      if(data.quote)return `<label class="${full}">${esc(item.label)}${star}<input name="${item.key}" value="${esc(data.record.package_name||value)}" readonly>${help}</label>`;
      return `<label class="${full}">${esc(item.label)}${star}<select name="${item.key}" ${required}><option value="">Please choose</option>${data.catalog.packages.map(p=>`<option value="${esc(p.name)}" ${value===p.name?"selected":""}>${esc(p.name)} - ${money(p.price)}</option>`).join("")}</select>${help}</label>`;
    }
    if(item.field_type==="payment_plan"){
      return `<fieldset class="full payment-plan-choices"><legend>${esc(item.label)}${star}</legend>${help}<div>${data.booking_form_template.payment_plans.map((plan,index)=>`<label class="payment-plan-choice"><input type="radio" name="payment_plan" value="${plan.code}" ${value===plan.code||(!value&&index===0)?"checked":""} required><span><strong>Option ${index+1}: ${esc(plan.label)}</strong><small>${esc(plan.description)}</small></span></label>`).join("")}</div></fieldset>`;
    }
    if(item.field_type==="textarea")return `<label class="${full}">${esc(item.label)}${star}<textarea name="${item.key}" rows="4" placeholder="${esc(item.placeholder||"")}" ${required}>${esc(value)}</textarea>${help}</label>`;
    if(item.field_type==="select")return `<label class="${full}">${esc(item.label)}${star}<select name="${item.key}" ${required}><option value="">Please choose</option>${item.options.map(option=>`<option value="${esc(option)}" ${value===option?"selected":""}>${esc(option)}</option>`).join("")}</select>${help}</label>`;
    if(item.field_type==="checkbox")return `<label class="${full} client-check"><input type="checkbox" name="${item.key}" value="yes" ${[true,"true","yes","on"].includes(value)?"checked":""} ${required}><span>${esc(item.label)}${star}</span>${help}</label>`;
    return `<label class="${full}">${esc(item.label)}${star}<input name="${item.key}" type="${item.field_type}" value="${esc(value)}" placeholder="${esc(item.placeholder||"")}" ${required}>${help}</label>`;
  }

  bookingForm = function () {
    if(data.record.kind!=="wedding"||!data.booking_form_template)return legacyBookingForm();
    const savedDraft=readBookingDraft(),x={...existing("booking_form"),...(savedDraft?.values||{})},template=data.booking_form_template;
    if(savedDraft)bookingStep=Math.max(0,Math.min(template.steps.length-1,Number(savedDraft.step)||0));
    const steps=template.steps.map((step,index)=>`<section class="form-step" data-step="${index}"><h3>${index+1}. ${esc(step.title)}</h3><p class="step-intro">${esc(step.introduction)}</p><div class="form-grid">${template.fields.filter(field=>field.step===step.id).map(field=>renderField(field,x)).join("")}</div></section>`).join("");
    const draftMessage=savedDraft?`<strong>✓ Your saved answers have been restored</strong><span>Recovered from this device at ${draftTime(savedDraft.savedAt)}. They will remain here until you submit the form.</span>`:`<strong>Your answers are protected while you type</strong><span>This form saves a private draft on this device for up to 30 days and removes it after successful submission.</span>`;
    $("#panel").innerHTML=`<h2>${esc(template.heading)}</h2><p class="intro">${esc(template.introduction)}</p>${existing("booking_form").primary_full_name?`<div class="complete">✓ Previously submitted - you can update it below.</div><br>`:""}<div id="booking-draft-status" class="client-draft-notice ${savedDraft?"restored":""}" role="status">${draftMessage}</div><form id="booking-form"><div class="form-progress">${template.steps.map(()=>"<span></span>").join("")}</div>${steps}<div class="form-step-actions"><button id="booking-back" class="secondary-client" type="button">Back</button><button id="booking-next" class="primary" type="button">Continue</button><button id="booking-save" class="primary" type="submit">${esc(template.submit_label)}</button></div></form>`;
    const form=$("#booking-form");
    form.onsubmit=event=>submitForm(event,"booking_form");
    wireBookingSteps();
    wireBookingDraft(form);
  };

  submitForm = async function(event,type){
    event.preventDefault();const form=new FormData(event.currentTarget),values={};
    const wasPreviouslySubmitted=Boolean(existing(type)&&Object.keys(existing(type)).length);
    for(const [key,value] of form.entries())values[key]=String(value).trim();
    if(type==="booking_form"&&data.record.kind==="wedding")writeBookingDraft(event.currentTarget);
    try{await api(`/api/client/${token}/forms`,{method:"POST",body:JSON.stringify({form_type:type,data:values})});if(type==="booking_form")clearBookingDraft();data=await api(`/api/client/${token}`);bookingStep=0;renderTabs();render();if(type==="booking_form"&&data.record.kind==="wedding")showBookingConfirmation(wasPreviouslySubmitted);else toast("Your details have been saved")}catch(error){toast(`${error.message}. Your answers are still saved on this device.`)}
  };

  function showBookingConfirmation(wasPreviouslySubmitted){
    document.querySelector(".booking-submit-confirmation")?.remove();
    const accepted=Boolean(data.contract);
    const message=data.booking_form_template?.success_message||"Thank you. Your answers have been securely added to your wedding file and are now available to Mark.";
    document.body.insertAdjacentHTML("beforeend",`<div class="booking-submit-confirmation" role="presentation"><section role="dialog" aria-modal="true" aria-labelledby="booking-confirmation-title" aria-describedby="booking-confirmation-message"><button class="booking-confirmation-close" type="button" aria-label="Close confirmation">×</button><span class="booking-confirmation-tick" aria-hidden="true">✓</span><small>SUCCESSFULLY ${wasPreviouslySubmitted?"UPDATED":"SUBMITTED"}</small><h2 id="booking-confirmation-title">Your Wedding Booking Form has been ${wasPreviouslySubmitted?"updated":"submitted"}</h2><p id="booking-confirmation-message">${esc(message)}</p><div class="booking-confirmation-note"><strong>It is safely in your wedding file</strong><span>You can return here and update these details later if anything changes.</span></div><div class="booking-confirmation-actions"><button class="secondary-client" data-confirmation-close type="button">Back to your booking</button><button class="primary" data-confirmation-next type="button">${accepted?"Return to overview":"Continue to agreement"}</button></div></section></div>`);
    const overlay=document.querySelector(".booking-submit-confirmation");
    const close=()=>overlay.remove();
    overlay.querySelector(".booking-confirmation-close").onclick=close;
    overlay.querySelector("[data-confirmation-close]").onclick=close;
    overlay.querySelector("[data-confirmation-next]").onclick=()=>{close();setActive(accepted?"Overview":"Agreement")};
    overlay.querySelector("[data-confirmation-next]").focus();
  }

  const originalInit=init;
  // The existing init has already started before this cumulative file loads.
  // The TEST banner is therefore added during the first render below.
  const originalRender=render;
  render=function(){originalRender();if(data?.record?.is_test&&!document.querySelector(".client-test-banner")){document.querySelector(".hero")?.insertAdjacentHTML("afterend",`<div class="client-test-banner"><strong>TEST BOOKING</strong><span>Emails from this test journey are safely routed to the nominated test address.</span></div>`)}};
})();
