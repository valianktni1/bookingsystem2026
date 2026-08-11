/* V8.9.8 — editable Wedding Booking Form, payment plans and protected Testing Mode. */
(() => {
  titles.bookingforms = "Wedding Booking Form";
  subtitles.bookingforms = "Edit the questionnaire couples complete after accepting their quote.";
  let bookingDraft = null;
  let testMode = {enabled:false,email:"",record_count:0};

  const baseLoad = loadAll;
  loadAll = async function () {
    const result = await baseLoad();
    try { testMode = await api("/api/testing-mode"); } catch (_) {}
    renderTestModeChrome();
    return result;
  };

  const baseRender = render;
  render = function () {
    if (state.view === "bookingforms") {
      $("#add-record")?.classList.add("hidden");
      $("#page-eyebrow").textContent = "WEDDINGS BY MARK";
      $("#page-title").textContent = titles.bookingforms;
      $("#page-subtitle").textContent = subtitles.bookingforms;
      renderBookingEditor();
    } else {
      $("#add-record")?.classList.remove("hidden");
      baseRender();
    }
    renderTestModeChrome();
  };

  function renderTestModeChrome() {
    const button = $("#testing-mode-button");
    const banner = $("#testing-mode-banner");
    if (!button || !banner) return;
    button.classList.toggle("active", testMode.enabled);
    button.innerHTML = testMode.enabled ? `● Testing Mode ON` : `○ Testing Mode`;
    banner.classList.toggle("hidden", !testMode.enabled);
    banner.innerHTML = testMode.enabled ? `<strong>TESTING MODE IS ON</strong><span>New website enquiries are marked TEST and every client email is safely redirected to <b>${esc(testMode.email)}</b>.</span><button id="testing-mode-change">Change or switch off</button>` : "";
    button.onclick = openTestingMode;
    $("#testing-mode-change")?.addEventListener("click", openTestingMode);
  }

  function openTestingMode() {
    showModal("Safe Testing Mode", `<div class="testing-explainer full"><strong>No real couple will receive test-journey emails</strong><span>Only enquiries created while this switch is on are marked TEST. Existing live and imported records are unchanged.</span></div><label class="check-option full"><input id="testing-enabled" type="checkbox" ${testMode.enabled?"checked":""}><span>Testing Mode is on</span></label><label class="full">Send all test-client emails to<input id="testing-email" type="email" value="${attr(testMode.email)}" required></label><div class="testing-count full"><b>${testMode.record_count||0}</b><span>test record${testMode.record_count===1?"":"s"} currently retained. They are clearly labelled and can be permanently deleted using the normal safe record controls.</span></div>`, async () => {
      testMode = await api("/api/testing-mode", {method:"PUT",body:JSON.stringify({enabled:$("#testing-enabled").checked,email:value("#testing-email")})});
      closeModal(); renderTestModeChrome(); toast(testMode.enabled?"Testing Mode is safely on":"Testing Mode switched off");
    }, "Switch it on before submitting your test enquiry form, then switch it off before going live.");
  }

  const baseRecords = renderRecords;
  renderRecords = function () { baseRecords(); decorateTestRecords($("#content")); };
  const baseRecordRow = recordRow;
  recordRow = function (r) { return baseRecordRow(r).replace("<strong>", `<strong>${r.is_test?`<em class="test-record-chip">TEST</em>`:""}`); };
  function decorateTestRecords(root) {
    $$('[data-record]',root).forEach(row => {
      const record = state.records.find(item => item.id === row.dataset.record);
      const cell = row.querySelector(".client-cell strong, .record-main strong");
      if (record?.is_test && cell && !cell.querySelector(".test-record-chip")) cell.insertAdjacentHTML("afterbegin", `<em class="test-record-chip">TEST</em>`);
    });
  }

  const baseOpenDrawer = openDrawer;
  openDrawer = async function (id, tab="Overview") {
    await baseOpenDrawer(id,tab);
    if (!state.current?.is_test || $("#drawer .test-record-banner")) return;
    const header = $("#drawer .record-command-header, #drawer .drawer-head");
    header?.insertAdjacentHTML("afterend", `<div class="test-record-banner"><strong>TEST RECORD</strong><span>Client emails are locked to the nominated Testing Mode address, never the entered couple address.</span></div>`);
  };

  const baseFinance = renderFinance;
  renderFinance = function (record, body) {
    baseFinance(record, body);
    $$(".invoice-card", body).forEach((card, index) => {
      const invoice = record.invoices[index];
      if (!invoice) return;
      const entries = [...card.querySelectorAll("dt")];
      const finalLabel = entries.find(node => node.textContent.trim() === "Final payment due");
      const finalCell = finalLabel?.nextElementSibling;
      if (finalCell) finalCell.innerHTML = `<strong>${invoice.final_due_date ? esc(fmtDate(invoice.final_due_date)) : "Not set"}</strong>${invoice.due_date_overridden ? ` <span class="agreed-date">Agreed date</span>` : ""}`;
      const button = card.querySelector("[data-due-invoice]");
      if (button) button.dataset.dueDate = invoice.final_due_date || "";
    });
  };

  function captureCopy() {
    if (!bookingDraft) return;
    bookingDraft.heading = value("#booking-heading");
    bookingDraft.introduction = value("#booking-introduction");
    bookingDraft.submit_label = value("#booking-submit-label");
    bookingDraft.success_message = value("#booking-success-message");
    bookingDraft.steps.forEach(step => {
      step.title = value(`#step-title-${step.id}`);
      step.introduction = value(`#step-intro-${step.id}`);
    });
    bookingDraft.payment_plans.forEach(plan => {
      plan.label = value(`#plan-label-${plan.code}`);
      plan.description = value(`#plan-description-${plan.code}`);
    });
  }

  async function renderBookingEditor() {
    const host = $("#content");
    if (!bookingDraft) {
      host.innerHTML = `<div class="panel loading">Loading the Wedding Booking Form…</div>`;
      try { bookingDraft = await api("/api/forms/wedding-booking"); }
      catch (error) { showError(error); return; }
      if (state.view !== "bookingforms") return;
    }
    host.innerHTML = `<section class="form-builder-toolbar"><div class="ready"><strong>Used after a quote is accepted</strong><span>The selected payment plan updates that couple's invoice and payment dates automatically.</span></div><button id="publish-booking-form" class="primary">Save & publish</button></section>
      <div class="booking-builder-layout">
        <section class="panel form-copy-panel"><div class="panel-title"><div><h2>Form wording</h2><p>Introduction and confirmation wording</p></div></div><div class="form-copy-grid"><label class="full">Heading<input id="booking-heading" value="${attr(bookingDraft.heading)}"></label><label class="full">Introduction<textarea id="booking-introduction" rows="3">${esc(bookingDraft.introduction)}</textarea></label><label>Save button<input id="booking-submit-label" value="${attr(bookingDraft.submit_label)}"></label><label>Saved message<input id="booking-success-message" value="${attr(bookingDraft.success_message)}"></label></div></section>
        <section class="panel payment-plan-editor"><div class="panel-title"><div><h2>Payment choices</h2><p>All three are protected because they drive invoice calculations</p></div></div><div class="plan-editor-list">${bookingDraft.payment_plans.map((plan,index)=>`<article><b>${index+1}</b><label>Choice wording<input id="plan-label-${plan.code}" value="${attr(plan.label)}"></label><label>Explanation<textarea id="plan-description-${plan.code}" rows="2">${esc(plan.description)}</textarea></label><em>Calculation protected</em></article>`).join("")}</div></section>
      </div>
      <section class="panel booking-question-panel"><div class="panel-title"><div><h2>Steps and questions</h2><p>Edit wording, arrange questions and add your own</p></div><button id="add-booking-question" class="primary">＋ Add question</button></div>${bookingDraft.steps.map(step=>`<section class="booking-step-editor"><header><span>STEP</span><label>Step title<input id="step-title-${step.id}" value="${attr(step.title)}"></label><label>Short introduction<input id="step-intro-${step.id}" value="${attr(step.introduction)}"></label></header><div class="form-question-list">${bookingDraft.fields.map((field,index)=>({field,index})).filter(x=>x.field.step===step.id).map(x=>questionRow(x.field,x.index)).join("")}</div></section>`).join("")}</section>`;
    $("#publish-booking-form").onclick = publishBookingForm;
    $("#add-booking-question").onclick = addQuestion;
    $$('[data-booking-edit]').forEach(b=>b.onclick=()=>editQuestion(Number(b.dataset.bookingEdit)));
    $$('[data-booking-up]').forEach(b=>b.onclick=()=>moveQuestion(Number(b.dataset.bookingUp),-1));
    $$('[data-booking-down]').forEach(b=>b.onclick=()=>moveQuestion(Number(b.dataset.bookingDown),1));
    $$('[data-booking-toggle]').forEach(b=>b.onclick=()=>toggleQuestion(Number(b.dataset.bookingToggle)));
    $$('[data-booking-delete]').forEach(b=>b.onclick=()=>deleteQuestion(Number(b.dataset.bookingDelete)));
  }

  function questionRow(field,index) {
    const protectedField = !field.custom && ["primary_full_name","primary_phone","primary_email","partner_full_name","street_address","town","county","postcode","wedding_date","ceremony_time","ceremony_details","reception_details","package_selected","payment_plan"].includes(field.key);
    return `<article class="form-question-row ${field.enabled?"":"hidden-question"}"><span class="question-position">${index+1}</span><div><strong>${esc(field.label)}${field.required?" *":""}</strong><small>${esc(field.field_type.replaceAll("_"," "))} · ${field.width} width</small><em>${protectedField?"Essential workflow field":field.custom?"Custom question":"Optional standard field"}</em></div><nav><button class="mini" data-booking-up="${index}">↑</button><button class="mini" data-booking-down="${index}">↓</button><button class="mini" data-booking-edit="${index}">Edit</button>${protectedField?`<span class="protected-chip">Protected</span>`:`<button class="mini" data-booking-toggle="${index}">${field.enabled?"Hide":"Show"}</button>`}${field.custom?`<button class="mini danger-text" data-booking-delete="${index}">Delete</button>`:""}</nav></article>`;
  }
  function moveQuestion(index,delta){captureCopy();const field=bookingDraft.fields[index],siblings=bookingDraft.fields.map((x,i)=>({x,i})).filter(x=>x.x.step===field.step),pos=siblings.findIndex(x=>x.i===index),target=siblings[pos+delta]?.i;if(target==null)return;[bookingDraft.fields[index],bookingDraft.fields[target]]=[bookingDraft.fields[target],bookingDraft.fields[index]];renderBookingEditor()}
  function toggleQuestion(index){captureCopy();bookingDraft.fields[index].enabled=!bookingDraft.fields[index].enabled;renderBookingEditor()}
  function deleteQuestion(index){captureCopy();const f=bookingDraft.fields[index];if(f.custom&&confirm(`Delete “${f.label}”? Existing submitted answers remain saved.`)){bookingDraft.fields.splice(index,1);renderBookingEditor()}}
  function questionModal(field,title,onSave){showModal(title,`<label class="full">Question wording<input id="bq-label" value="${attr(field.label)}" required></label><label>Step<select id="bq-step">${bookingDraft.steps.map(s=>`<option value="${s.id}" ${s.id===field.step?"selected":""}>${esc(s.title)}</option>`).join("")}</select></label><label>Width<select id="bq-width"><option value="half" ${field.width==="half"?"selected":""}>Half</option><option value="full" ${field.width==="full"?"selected":""}>Full</option></select></label><label>Answer type<select id="bq-type" ${field.custom?"":"disabled"}>${[["text","Short answer"],["textarea","Long answer"],["select","Choice list"],["checkbox","Tick box"],["number","Number"]].map(x=>`<option value="${x[0]}" ${field.field_type===x[0]?"selected":""}>${x[1]}</option>`).join("")}${field.custom?"":`<option value="${field.field_type}" selected>Protected type</option>`}</select></label><label class="full">Placeholder<input id="bq-placeholder" value="${attr(field.placeholder||"")}"></label><label class="full">Help text<input id="bq-help" value="${attr(field.help_text||"")}"></label><label class="full">Choices — one per line<textarea id="bq-options" rows="5">${esc((field.options||[]).join("\n"))}</textarea></label><label class="check-option full"><input id="bq-required" type="checkbox" ${field.required?"checked":""} ${!field.custom&&field.required?"disabled":""}><span>Couple must answer</span></label>`,async()=>{const updated={...field,label:value("#bq-label").trim(),step:value("#bq-step"),width:value("#bq-width"),field_type:field.custom?value("#bq-type"):field.field_type,placeholder:value("#bq-placeholder").trim(),help_text:value("#bq-help").trim(),required:$("#bq-required").checked,options:value("#bq-options").split("\n").map(x=>x.trim()).filter(Boolean)};if(!updated.label)throw new Error("Add question wording");if(updated.field_type==="select"&&!updated.options.length)throw new Error("Add at least one choice");onSave(updated);closeModal();renderBookingEditor()},field.custom?"Custom questions can be edited or deleted later.":"Workflow field types stay protected so invoices and bookings remain reliable.")}
  function editQuestion(index){captureCopy();questionModal(bookingDraft.fields[index],"Edit booking question",updated=>bookingDraft.fields[index]=updated)}
  function addQuestion(){captureCopy();const id=`custom_${crypto.randomUUID().replaceAll("-","").slice(0,16)}`,field={id,key:id,label:"New question",field_type:"text",step:bookingDraft.steps[0].id,placeholder:"",help_text:"",required:false,enabled:true,width:"full",options:[],custom:true};questionModal(field,"Add booking question",updated=>bookingDraft.fields.push(updated))}
  async function publishBookingForm(){captureCopy();const button=$("#publish-booking-form");button.disabled=true;button.textContent="Publishing…";try{bookingDraft=await api("/api/forms/wedding-booking",{method:"PUT",body:JSON.stringify({heading:bookingDraft.heading,introduction:bookingDraft.introduction,submit_label:bookingDraft.submit_label,success_message:bookingDraft.success_message,steps:bookingDraft.steps,payment_plans:bookingDraft.payment_plans,fields:bookingDraft.fields})});toast("Wedding Booking Form published");renderBookingEditor()}catch(error){toast(error.message,"error");button.disabled=false;button.textContent="Save & publish"}}
})();
