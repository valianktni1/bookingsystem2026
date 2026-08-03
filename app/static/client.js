const $ = selector => document.querySelector(selector);
let data = null;
const requestedTab = new URLSearchParams(location.search).get("tab");
const requestedTabs = {quote: "Choose package", invoices: "Invoices", "final-details": "Final details", agreement: "Agreement"};
let active = requestedTabs[requestedTab] || "Overview";
const token = location.pathname.split("/").filter(Boolean).pop();

const esc = (value = "") => String(value ?? "").replace(/[&<>'"]/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
}[char]));
const money = value => new Intl.NumberFormat("en-GB", {style: "currency", currency: "GBP"}).format(Number(value || 0));
const date = value => value ? new Intl.DateTimeFormat("en-GB", {day: "numeric", month: "long", year: "numeric"}).format(new Date(value + "T12:00:00")) : "To be confirmed";

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {"Content-Type": "application/json"}, ...options});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(Array.isArray(body.detail) ? body.detail.map(x => x.msg).join(", ") : body.detail || "Something went wrong");
  return body;
}
function toast(text) {
  $("#toast").textContent = text;
  $("#toast").classList.remove("hidden");
  setTimeout(() => $("#toast").classList.add("hidden"), 3000);
}
function existing(type) { return data.submissions.find(x => x.form_type === type)?.data || {}; }

async function init() {
  try {
    data = await api(`/api/client/${token}`);
    $("#loading").classList.add("hidden");
    $("#portal").classList.remove("hidden");
    $("#business-name").textContent = data.business.name;
    $("#booking-label").textContent = data.record.kind === "wedding" ? "YOUR WEDDING BOOKING" : "YOUR PROJECT";
    $("#record-title").textContent = data.record.title;
    $("#record-summary").textContent = `${date(data.record.event_date)} · ${data.record.venue_or_project || "Details to be confirmed"}`;
    renderTabs();
    render();
  } catch (error) {
    $("#loading").classList.add("hidden");
    $("#error").classList.remove("hidden");
    $("#error-message").textContent = error.message;
  }
}

function renderTabs() {
  const hasQuote = data.record.kind === "wedding" && data.catalog.packages.length;
  const tabs = ["Overview", ...(hasQuote ? ["Choose package"] : []), "Invoices", "Booking form",
    ...(data.record.kind === "wedding" ? ["Final details"] : []), "Agreement"];
  $("#tabs").innerHTML = tabs.map(tab => `<button class="${tab === active ? "active" : ""}" data-tab="${tab}">${tab}</button>`).join("");
  document.querySelectorAll("[data-tab]").forEach(button => button.onclick = () => {
    active = button.dataset.tab;
    renderTabs();
    render();
  });
}
function render() {
  if (active === "Overview") overview();
  else if (active === "Choose package") quotePanel();
  else if (active === "Invoices") invoicesPanel();
  else if (active === "Booking form") bookingForm();
  else if (active === "Final details") finalForm();
  else agreement();
}

function overview() {
  const quoteState = data.quote ? "accepted" : "waiting";
  $("#panel").innerHTML = `<h2>Welcome, ${esc(data.record.client.first_name)}</h2>
    <p class="intro">This is your ${data.record.kind === "wedding" ? "wedding booking" : "project"} area for choosing your package, completing your details and accepting the agreement.</p>
    <div class="summary"><div><small>PACKAGE / SERVICE</small><strong>${esc(data.record.package_name || "To be confirmed")}</strong></div><div><small>TOTAL</small><strong>${money(data.record.quoted_total)}</strong></div><div><small>BOOKING FEE / DEPOSIT</small><strong>${money(data.record.deposit_amount)}</strong></div></div>
    <div style="margin-top:16px" class="complete">${data.record.kind === "wedding" ? `Package: ${quoteState} · ` : ""}Booking form: ${existing("booking_form").primary_phone || existing("booking_form").contact_phone ? "completed" : "waiting"} · Agreement: ${data.contract ? "accepted" : "waiting"}${data.record.kind === "wedding" ? ` · Final details: ${existing("final_questionnaire").timeline ? "completed" : "waiting"}` : ""}</div>`;
}

function quotePanel() {
  if (data.quote) {
    const invoice = data.invoices.find(item => item.id === data.quote.invoice_id) || data.invoices[0];
    $("#panel").innerHTML = `<h2>Your package is confirmed</h2><p class="intro">Your selection has been saved and invoice ${data.quote.invoice_number ? esc(data.quote.invoice_number) : "has been created"}.</p>
      <div class="complete">Accepted on ${date(data.quote.accepted_at.slice(0, 10))}</div>
      <div class="quote-lines">${data.quote.line_items.map(item => `<div><span><strong>${esc(item.name)}</strong><small>${item.type === "addon" ? "Add-on" : "Package"}</small></span><b>${money(item.total)}</b></div>`).join("")}</div>
      <div class="quote-total"><span><small>Total</small><strong>${money(data.quote.total)}</strong></span><span><small>Booking fee</small><strong>${money(data.quote.deposit_amount)}</strong>${invoice?.deposit_due_date ? `<em>Due ${date(invoice.deposit_due_date)}</em>` : ""}</span>${invoice?.due_date ? `<span><small>Remaining balance</small><strong>${money(Number(data.quote.total) - Number(data.quote.deposit_amount))}</strong><em>Due ${date(invoice.due_date)}</em></span>` : ""}</div>`;
    return;
  }
  const packages = data.catalog.packages;
  $("#panel").innerHTML = `<h2>Choose your wedding package</h2><p class="intro">Select one package, then choose any available extras. Your total updates automatically. An invoice is created when you accept.</p>
    <form id="quote-form"><div class="package-grid">${packages.map((item, index) => `<label class="package-card"><input type="radio" name="package_id" value="${item.id}" ${index === 0 ? "checked" : ""}><span class="package-check">✓</span><span class="package-name"><strong>${esc(item.name)}</strong><b>${money(item.price)}</b></span><small>${esc(item.description)}</small><em>${money(item.deposit_amount)} booking fee · due within one day of accepting</em></label>`).join("")}</div>
    <section class="addon-section"><h3>Optional add-ons</h3><p>Only extras available for your selected package are shown.</p><div id="addon-list"></div></section>
    <div class="quote-footer"><div><small>TOTAL</small><strong id="quote-total">£0.00</strong><span id="quote-deposit"></span></div><label class="quote-confirm"><input type="checkbox" name="confirmed" required><span>I confirm that this package, the selected add-ons and the total shown are correct.</span></label><button class="primary" type="submit">Accept package & create invoice</button></div></form>`;
  document.querySelectorAll('input[name="package_id"]').forEach(input => input.onchange = renderAddons);
  $("#quote-form").onsubmit = acceptSelectedQuote;
  renderAddons();
}

function invoicesPanel() {
  if (!data.invoices.length) {
    $("#panel").innerHTML = `<h2>Your invoices</h2><p class="intro">Your invoice will appear here automatically after you accept your package or service quote.</p><div class="invoice-empty"><strong>No invoice yet</strong><span>Choose and accept your package first.</span></div>`;
    return;
  }
  $("#panel").innerHTML = `<h2>Your invoices & payments</h2><p class="intro">Download your invoice for the bank-transfer details and use the invoice number as your payment reference.</p><div class="client-invoices">${data.invoices.map(invoice => `<article class="client-invoice"><header><div><strong>${esc(invoice.number)}</strong><span class="invoice-status ${invoice.status}">${esc(String(invoice.status).replaceAll("_", " "))}</span></div><b>${money(invoice.total)}</b></header>${invoice.line_items?.length ? `<div class="client-invoice-lines">${invoice.line_items.map(item => `<div><span><b>${esc(item.name)}</b>${item.description ? `<small>${esc(item.description)}</small>` : ""}</span><strong>${money(item.total)}</strong></div>`).join("")}</div>` : invoice.description ? `<p>${esc(invoice.description)}</p>` : ""}<dl><dt>Issued</dt><dd>${date(invoice.issue_date)}</dd>${invoice.deposit_due_date ? `<dt>Booking fee</dt><dd>${money(invoice.deposit_amount)} · due ${date(invoice.deposit_due_date)}</dd>` : ""}${invoice.due_date ? `<dt>Remaining balance</dt><dd>${money(Math.max(0, Number(invoice.total) - Number(invoice.deposit_amount || 0)))} · due ${date(invoice.due_date)}</dd>` : ""}<dt>Paid so far</dt><dd>${money(invoice.paid)}</dd><dt>Total outstanding</dt><dd><strong>${money(invoice.balance)}</strong></dd></dl><div class="client-invoice-actions"><a class="primary" href="/api/client/${token}/invoices/${invoice.id}/invoice.pdf">Download invoice PDF</a>${invoice.paid > 0 ? `<a class="secondary-client" href="/api/client/${token}/invoices/${invoice.id}/receipt.pdf">Download receipt</a>` : ""}</div></article>`).join("")}</div>`;
}

function selectedPackage() {
  const id = document.querySelector('input[name="package_id"]:checked')?.value;
  return data.catalog.packages.find(item => item.id === id);
}
function renderAddons() {
  const selected = selectedPackage();
  const eligible = data.catalog.addons.filter(item => !item.eligible_package_codes.length || item.eligible_package_codes.includes(selected.code));
  $("#addon-list").innerHTML = eligible.length ? eligible.map(item => `<label class="addon-card"><input type="checkbox" name="addon_id" value="${item.id}"><span><strong>${esc(item.name)}</strong><small>${esc(item.description)}</small></span><b>+${money(item.price)}</b></label>`).join("") : `<p class="no-addons">No additional extras are needed or available for this package.</p>`;
  document.querySelectorAll('input[name="addon_id"]').forEach(input => input.onchange = updateQuoteTotal);
  updateQuoteTotal();
}
function updateQuoteTotal() {
  const selected = selectedPackage();
  const selectedIds = [...document.querySelectorAll('input[name="addon_id"]:checked')].map(x => x.value);
  const addonTotal = data.catalog.addons.filter(x => selectedIds.includes(x.id)).reduce((sum, x) => sum + Number(x.price), 0);
  $("#quote-total").textContent = money(Number(selected.price) + addonTotal);
  $("#quote-deposit").textContent = `${money(selected.deposit_amount)} booking fee due within one day of accepting`;
}
async function acceptSelectedQuote(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  if (!confirm("Accept this package and create the invoice? The selection cannot be changed from your wedding booking afterwards.")) return;
  try {
    await api(`/api/client/${token}/quote`, {method: "POST", body: JSON.stringify({
      package_id: form.get("package_id"), addon_ids: form.getAll("addon_id"), confirmed: form.get("confirmed") === "on"
    })});
    data = await api(`/api/client/${token}`);
    toast("Package accepted and invoice created");
    active = "Invoices";
    renderTabs();
    render();
  } catch (error) { toast(error.message); }
}

function field(label, name, value = "", full = false, type = "text", required = false) {
  return `<label class="${full ? "full" : ""}">${label}${required ? " *" : ""}<input name="${name}" type="${type}" value="${esc(value)}" ${required ? "required" : ""}></label>`;
}
function bookingForm() {
  const x = existing("booking_form"), wedding = data.record.kind === "wedding";
  if (!wedding) {
    $("#panel").innerHTML = `<h2>Project information</h2><p class="intro">Please check and complete the details below.</p>${x.contact_phone ? `<div class="complete">Previously submitted. You can update it below.</div><br>` : ""}<form id="booking-form"><div class="form-grid">${field("Your full name", "full_name", x.full_name || `${data.record.client.first_name} ${data.record.client.last_name || ""}`, false, "text", true)}${field("Company name", "partner_or_company", x.partner_or_company || data.record.client.company_name || "")}${field("Contact telephone", "contact_phone", x.contact_phone || data.record.client.phone || "")}${field("Address", "address", x.address || data.record.client.address || "", true)}${field("Project/service required", "service_required", x.service_required || data.record.package_name || "", true)}${field("Current website", "current_website", x.current_website || "")}${field("Preferred completion date", "target_date", x.target_date || data.record.event_date || "", false, "date")}<label class="full">Anything else we should know?<textarea name="additional_notes" rows="4">${esc(x.additional_notes || "")}</textarea></label></div><div class="actions"><button class="primary" type="submit">Save project information</button></div></form>`;
    $("#booking-form").onsubmit = event => submitForm(event, "booking_form");
    return;
  }
  const paymentSchedule = "Booking fee due within one day of accepting the quote; remaining balance due 45 days before the wedding";
  $("#panel").innerHTML = `<h2>Wedding Booking Form</h2><p class="intro">Thank you for taking the time to complete this questionnaire. Your answers will help me understand your day and plan everything perfectly.</p>${x.primary_full_name ? `<div class="complete">Previously submitted. You can update it below.</div><br>` : ""}<form id="booking-form"><div class="form-grid">
    ${field("Bride's/Groom's full name", "primary_full_name", x.primary_full_name || `${data.record.client.first_name} ${data.record.client.last_name || ""}`, false, "text", true)}
    ${field("Street address", "street_address", x.street_address || data.record.client.address || "", true, "text", true)}
    ${field("Town", "town", x.town || "", false, "text", true)}
    ${field("City/County", "county", x.county || "", false, "text", true)}
    ${field("Postcode", "postcode", x.postcode || "", false, "text", true)}
    ${field("Bride's/Groom's phone number", "primary_phone", x.primary_phone || data.record.client.phone || "", false, "tel", true)}
    ${field("Bride's/Groom's email", "primary_email", x.primary_email || data.record.client.email, false, "email", true)}
    ${field("Groom's/Bride's full name", "partner_full_name", x.partner_full_name || data.record.client.partner_name || "", false, "text", true)}
    ${field("Groom's/Bride's phone number", "partner_phone", x.partner_phone || "", false, "tel", true)}
    ${field("Groom's/Bride's email", "partner_email", x.partner_email || "", false, "email")}
    ${field("Date of wedding/event", "wedding_date", x.wedding_date || data.record.event_date || "", false, "date", true)}
    <label class="full">Exact ceremony details and venue(s)<textarea name="ceremony_details" rows="4" required>${esc(x.ceremony_details || data.record.venue_or_project || "")}</textarea></label>
    ${field("Ceremony/service time", "ceremony_time", x.ceremony_time || "", false, "time", true)}
    <label class="full">Exact reception venue details<textarea name="reception_details" rows="4" required placeholder="If this is the same as the ceremony venue, please say so">${esc(x.reception_details || "")}</textarea></label>
    ${data.quote ? `<label class="full">Package selected<input name="package_selected" value="${esc(data.record.package_name)}" readonly></label>` : `<label class="full">Package selected<select name="package_selected" required><option value="">Please choose</option>${data.catalog.packages.map(p => `<option value="${esc(p.name)}" ${(x.package_selected || data.record.package_name) === p.name ? "selected" : ""}>${esc(p.name)} - ${money(p.price)}</option>`).join("")}</select></label>`}
    <fieldset class="full form-options payment-schedule"><legend>Payment schedule</legend><strong>Simple bank-transfer payments</strong><span>Your booking fee is due within one day of accepting your quote. The remaining balance is due 45 days before your wedding.</span></fieldset>
    ${field("How many people will be in your wedding party?", "wedding_party_size", x.wedding_party_size || "", false, "number", true)}
    <label class="full">Are there any unique events happening at the wedding that I need to know about?<textarea name="unique_events" rows="4" required placeholder="For example, the bride will arrive on a horse">${esc(x.unique_events || "")}</textarea></label>
    <label class="full">Wedding guest photo uploads - Package 2 and upwards<select name="guest_uploads"><option value="">Please choose</option><option value="yes" ${x.guest_uploads === "yes" ? "selected" : ""}>Yes please</option><option value="no" ${x.guest_uploads === "no" ? "selected" : ""}>No thank you</option></select></label>
    <label class="full">Is there any additional information you would like to include?<textarea name="additional_information" rows="4">${esc(x.additional_information || "")}</textarea></label>
    <label class="full">Highlight video music choices for Gold, Platinum and Ultimate packages<textarea name="highlight_music" rows="4" placeholder="Please give two songs. The first song entered will be used first in the highlight video.">${esc(x.highlight_music || "")}</textarea></label>
    </div><div class="actions"><button class="primary" type="submit">Save Wedding Booking Form</button></div></form>`;
  $("#booking-form").onsubmit = event => submitForm(event, "booking_form");
}
function finalForm() {
  const x = existing("final_questionnaire");
  $("#panel").innerHTML = `<h2>Final wedding details</h2><p class="intro">Please give as much detail as possible so the day runs smoothly.</p>${x.timeline ? `<div class="complete">Previously submitted. You can update it below.</div><br>` : ""}<form id="final-form"><div class="form-grid"><label class="full">Full timeline for the day<textarea name="timeline" rows="6" required>${esc(x.timeline || "")}</textarea></label><label class="full">Important family/group photographs<textarea name="group_photos" rows="4">${esc(x.group_photos || "")}</textarea></label><label class="full">Supplier names and contact details<textarea name="suppliers" rows="4">${esc(x.suppliers || "")}</textarea></label>${field("Speeches planned for", "speeches_time", x.speeches_time || "")}${field("First dance time", "first_dance_time", x.first_dance_time || "")}<label class="full">Surprises, sensitivities or special requests<textarea name="special_requests" rows="4">${esc(x.special_requests || "")}</textarea></label><label class="full">Video music suggestions, if included<textarea name="music_suggestions" rows="3">${esc(x.music_suggestions || "")}</textarea></label></div><div class="actions"><button class="primary" type="submit">Save final details</button></div></form>`;
  $("#final-form").onsubmit = event => submitForm(event, "final_questionnaire");
}
async function submitForm(event, type) {
  event.preventDefault();
  const form = new FormData(event.currentTarget), values = {};
  for (const [key, value] of form.entries()) values[key] = String(value).trim();
  if (type === "booking_form" && data.record.kind === "wedding") {
    values.payment_options = ["Booking fee due within one day of accepting the quote; remaining balance due 45 days before the wedding"];
  }
  try {
    await api(`/api/client/${token}/forms`, {method: "POST", body: JSON.stringify({form_type: type, data: values})});
    data = await api(`/api/client/${token}`);
    toast("Your details have been saved");
    render();
  } catch (error) { toast(error.message); }
}
function agreement() {
  const contract = data.contract_template;
  if (!contract) return $("#panel").innerHTML = `<h2>Agreement unavailable</h2><p class="intro">Please contact ${esc(data.business.name)}.</p>`;
  if (data.contract) return $("#panel").innerHTML = `<h2>Agreement accepted</h2><div class="complete">Accepted by ${esc(data.contract.accepted_name)} on ${date(data.contract.accepted_at.slice(0, 10))}. Version ${esc(data.contract.version)}.</div><div class="contract" style="margin-top:16px">${esc(contract.body)}</div>`;
  $("#panel").innerHTML = `<h2>${esc(contract.title)}</h2><p class="intro">Version ${esc(contract.version)}. Please read the complete agreement before accepting it.</p><div class="contract">${esc(contract.body)}</div><form id="contract-form"><div class="form-grid" style="margin-top:17px">${field("Your full legal name", "accepted_name", `${data.record.client.first_name} ${data.record.client.last_name || ""}`)}${field("Your booking email", "accepted_email", data.record.client.email, false, "email")}</div><label class="agreement"><input name="agreed" type="checkbox" required><span>I have read and agree to the complete booking agreement above. I understand this electronic acceptance will be recorded with the date and technical audit information.</span></label><div class="actions"><button class="primary" type="submit">Accept agreement</button></div></form>`;
  $("#contract-form").onsubmit = async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api(`/api/client/${token}/contract`, {method: "POST", body: JSON.stringify({accepted_name: form.get("accepted_name"), accepted_email: form.get("accepted_email"), agreed: form.get("agreed") === "on"})});
      data = await api(`/api/client/${token}`);
      toast("Agreement accepted");
      render();
    } catch (error) { toast(error.message); }
  };
}

init();
