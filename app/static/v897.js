/* V8.9.7 — editable, protected website enquiry form. */
(() => {
  titles.forms = "Web enquiry form";
  subtitles.forms = "Edit the questions couples see on your website — no code or iframe replacement needed.";
  let formDraft = null;

  const baseRenderV897 = render;
  render = function () {
    const editingForms = state.view === "forms";
    if (!editingForms) return baseRenderV897();
    $("#add-record")?.classList.add("hidden");
    $("#page-eyebrow").textContent = "WEDDINGS BY MARK";
    $("#page-title").textContent = titles.forms;
    $("#page-subtitle").textContent = subtitles.forms;
    renderFormEditor();
  };

  const baseRenderPackagesV897 = renderPackages;
  renderPackages = async function () {
    await baseRenderPackagesV897();
    $("#content > .comm-status")?.remove();
  };

  const baseRenderTabV897 = renderTab;
  renderTab = async function (record, tab, target = null) {
    await baseRenderTabV897(record, tab, target);
    if (normaliseRecordTab(tab) !== "Forms") return;
    const body = target || $("#drawer-body");
    const enquiry = record.form_data?.website_enquiry;
    const answers = enquiry?.answer_snapshot || [];
    if (!body || !enquiry) return;
    const card = document.createElement("section");
    card.className = "website-enquiry-answers";
    card.innerHTML = `<header><div><small>ORIGINAL WEBSITE ENQUIRY</small><h3>Answers submitted before the quote</h3><p>The wording below is the exact version this couple saw.</p></div><strong>${answers.length} answers</strong></header><dl>${answers.map(item => `<div><dt>${esc(item.label)}</dt><dd>${questionnaireAnswer(item.answer)}</dd></div>`).join("") || `<div><dt>Enquiry details</dt><dd>${questionnaireAnswer(enquiry)}</dd></div>`}</dl>`;
    body.append(card);
  };

  function capturePageCopy() {
    if (!formDraft) return;
    const mapping = {
      "form-heading": "heading", "form-introduction": "introduction",
      "form-payment-title": "payment_title", "form-submit-label": "submit_label",
      "form-success-heading": "success_heading", "form-success-message": "success_message"
    };
    Object.entries(mapping).forEach(([id, key]) => { const input = $(`#${id}`); if (input) formDraft[key] = input.value; });
    const options = $("#form-payment-options");
    if (options) formDraft.payment_options = options.value.split("\n").map(line => line.trim()).filter(Boolean);
  }

  async function renderFormEditor() {
    const host = $("#content");
    if (!formDraft) {
      host.innerHTML = `<div class="panel loading">Loading the website enquiry form…</div>`;
      try { formDraft = await api("/api/forms/website-enquiry"); }
      catch (error) { showError(error); return; }
      if (state.view !== "forms") return;
    }
    host.innerHTML = `<section class="form-builder-toolbar"><div class="ready"><strong>Published on your website</strong><span>Saving here updates the existing iframe automatically.</span></div><a class="secondary" href="/enquiry" target="_blank" rel="noopener">Preview live form ↗</a><button id="copy-form-embed" class="secondary">Copy website code</button><button id="publish-form" class="primary">Save & publish</button></section>
      <div class="form-builder-layout">
        <section class="panel form-copy-panel"><div class="panel-title"><div><h2>Page wording</h2><p>Headings, payment information and thank-you message</p></div></div>
          <div class="form-copy-grid">
            <label class="full">Main heading<textarea id="form-heading" rows="3" maxlength="300">${esc(formDraft.heading)}</textarea></label>
            <label class="full">Introduction<textarea id="form-introduction" rows="3" maxlength="1000">${esc(formDraft.introduction)}</textarea></label>
            <label>Payment information heading<input id="form-payment-title" maxlength="200" value="${attr(formDraft.payment_title)}"></label>
            <label>Submit button wording<input id="form-submit-label" maxlength="80" value="${attr(formDraft.submit_label)}"></label>
            <label class="full">Payment choices — one per line<textarea id="form-payment-options" rows="6">${esc((formDraft.payment_options || []).join("\n"))}</textarea></label>
            <label>Thank-you heading<input id="form-success-heading" maxlength="200" value="${attr(formDraft.success_heading)}"></label>
            <label>Thank-you message<textarea id="form-success-message" rows="4" maxlength="1000">${esc(formDraft.success_message)}</textarea></label>
          </div>
        </section>
        <section class="panel form-question-panel"><div class="panel-title"><div><h2>Questions</h2><p>Arrange them in the order couples should complete them</p></div><button id="add-form-question" class="primary">＋ Add question</button></div>
          <div class="form-question-list">${formDraft.fields.map((field, index) => questionRow(field, index)).join("")}</div>
        </section>
      </div>`;
    $("#publish-form").onclick = publishForm;
    $("#copy-form-embed").onclick = copyEmbed;
    $("#add-form-question").onclick = addQuestion;
    $$('[data-form-edit]').forEach(button => button.onclick = () => editQuestion(Number(button.dataset.formEdit)));
    $$('[data-form-up]').forEach(button => button.onclick = () => moveQuestion(Number(button.dataset.formUp), -1));
    $$('[data-form-down]').forEach(button => button.onclick = () => moveQuestion(Number(button.dataset.formDown), 1));
    $$('[data-form-toggle]').forEach(button => button.onclick = () => toggleQuestion(Number(button.dataset.formToggle)));
    $$('[data-form-delete]').forEach(button => button.onclick = () => deleteQuestion(Number(button.dataset.formDelete)));
  }

  function questionRow(field, index) {
    const protectedField = !field.custom && ["primary_first_name", "partner_first_name", "email", "event_date", "location", "heard_about_us", "privacy_agreed"].includes(field.key);
    const typeName = ({text: "Short answer", email: "Email", tel: "Telephone", date: "Date", select: "Choice list", textarea: "Long answer", checkbox: "Tick box", venue: "Google venue search", package: "Live package list"})[field.field_type] || field.field_type;
    return `<article class="form-question-row ${field.enabled ? "" : "hidden-question"}"><span class="question-position">${index + 1}</span><div><strong>${esc(field.label)}${field.required ? " *" : ""}</strong><small>${esc(typeName)} · ${field.width === "full" ? "full width" : "half width"}</small><em>${protectedField ? "Essential workflow field" : field.custom ? "Custom question" : field.enabled ? "Optional standard field" : "Hidden from website"}</em></div><nav><button class="mini" data-form-up="${index}" ${index === 0 ? "disabled" : ""} title="Move up">↑</button><button class="mini" data-form-down="${index}" ${index === formDraft.fields.length - 1 ? "disabled" : ""} title="Move down">↓</button><button class="mini" data-form-edit="${index}">Edit</button>${protectedField ? `<span class="protected-chip">Protected</span>` : `<button class="mini" data-form-toggle="${index}">${field.enabled ? "Hide" : "Show"}</button>`}${field.custom ? `<button class="mini danger-text" data-form-delete="${index}">Delete</button>` : ""}</nav></article>`;
  }

  function moveQuestion(index, change) {
    capturePageCopy();
    const target = index + change;
    if (target < 0 || target >= formDraft.fields.length) return;
    [formDraft.fields[index], formDraft.fields[target]] = [formDraft.fields[target], formDraft.fields[index]];
    renderFormEditor();
  }

  function toggleQuestion(index) {
    capturePageCopy();
    formDraft.fields[index].enabled = !formDraft.fields[index].enabled;
    renderFormEditor();
  }

  function deleteQuestion(index) {
    capturePageCopy();
    const field = formDraft.fields[index];
    if (!field.custom || !confirm(`Delete the custom question “${field.label}”?\n\nOld enquiries keep their original answers.`)) return;
    formDraft.fields.splice(index, 1);
    renderFormEditor();
  }

  function questionModal(field, title, onSave) {
    const editableType = field.custom;
    showModal(title, `<label class="full">Question wording<input id="question-label" maxlength="240" value="${attr(field.label)}" required></label>
      <label>Answer type<select id="question-type" ${editableType ? "" : "disabled"}>${[["text","Short answer"],["textarea","Long answer"],["select","Choice list"],["checkbox","Tick box"]].map(([value,label]) => `<option value="${value}" ${field.field_type === value ? "selected" : ""}>${label}</option>`).join("")}${editableType ? "" : `<option value="${field.field_type}" selected>Protected type</option>`}</select></label>
      <label>Width<select id="question-width"><option value="half" ${field.width === "half" ? "selected" : ""}>Half width</option><option value="full" ${field.width === "full" ? "selected" : ""}>Full width</option></select></label>
      <label class="full">Placeholder / first choice<input id="question-placeholder" maxlength="240" value="${attr(field.placeholder || "")}"></label>
      <label class="full">Help text<input id="question-help" maxlength="500" value="${attr(field.help_text || "")}"></label>
      <label class="full question-options ${field.field_type === "select" ? "" : "hidden"}">Choices — one per line<textarea id="question-options" rows="6">${esc((field.options || []).join("\n"))}</textarea></label>
      <label class="check-option full"><input id="question-required" type="checkbox" ${field.required ? "checked" : ""} ${!field.custom && ["primary_first_name","partner_first_name","email","event_date","location","heard_about_us","privacy_agreed"].includes(field.key) ? "disabled" : ""}><span>Couple must answer this question</span></label>`, async () => {
        const type = editableType ? value("#question-type") : field.field_type;
        const updated = {...field, label: value("#question-label").trim(), field_type: type, width: value("#question-width"), placeholder: value("#question-placeholder").trim(), help_text: value("#question-help").trim(), required: $("#question-required").checked, options: value("#question-options").split("\n").map(item => item.trim()).filter(Boolean)};
        if (!updated.label) throw new Error("Add the question wording");
        if (updated.field_type === "select" && !updated.options.length) throw new Error("Add at least one choice");
        onSave(updated); closeModal(); renderFormEditor();
      }, field.custom ? "Custom questions can be edited or deleted later. Existing enquiry answers remain unchanged." : "The internal field type is protected so enquiries continue to create bookings correctly.");
    $("#question-type")?.addEventListener("change", event => $(".question-options", $("#modal")).classList.toggle("hidden", event.target.value !== "select"));
  }

  function editQuestion(index) {
    capturePageCopy();
    questionModal(formDraft.fields[index], "Edit question", updated => { formDraft.fields[index] = updated; });
  }

  function addQuestion() {
    capturePageCopy();
    const id = `custom_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`;
    const field = {id, key: id, label: "New question", field_type: "text", placeholder: "", help_text: "", required: false, enabled: true, width: "full", options: [], custom: true};
    questionModal(field, "Add a website question", updated => formDraft.fields.push(updated));
  }

  async function publishForm() {
    capturePageCopy();
    const button = $("#publish-form");
    button.disabled = true; button.textContent = "Publishing…";
    try {
      formDraft = await api("/api/forms/website-enquiry", {method: "PUT", body: JSON.stringify({heading: formDraft.heading, introduction: formDraft.introduction, payment_title: formDraft.payment_title, payment_options: formDraft.payment_options, fields: formDraft.fields, submit_label: formDraft.submit_label, success_heading: formDraft.success_heading, success_message: formDraft.success_message})});
      toast("Website enquiry form published");
      renderFormEditor();
    } catch (error) { toast(error.message, "error"); button.disabled = false; button.textContent = "Save & publish"; }
  }

  async function copyEmbed() {
    const origin = location.origin;
    const code = `<iframe id="wbm-enquiry-form" src="${origin}/enquiry" style="width:100%;max-width:1040px;height:1600px;border:0" loading="lazy" title="Weddings By Mark enquiry form"></iframe>\n<script data-iframe-id="wbm-enquiry-form" src="${origin}/static/enquiry-embed.js?v=enquiry-confirmation-v8-28-2"></script>`;
    await navigator.clipboard.writeText(code);
    toast("Website embed code copied");
  }
})();
