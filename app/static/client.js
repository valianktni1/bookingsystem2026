const $ = selector => document.querySelector(selector);
let data = null;
let bookingStep = 0;
const requestedTab = new URLSearchParams(location.search).get("tab");
const requestedTabs = {quote:"Choose package", invoices:"Invoices", booking:"Booking form", "final-details":"Final details", documents:"Documents", agreement:"Agreement"};
let active = requestedTabs[requestedTab] || "Overview";
const token = location.pathname.split("/").filter(Boolean).pop();

const esc = (value = "") => String(value ?? "").replace(/[&<>'"]/g, char => ({
  "&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;"
}[char]));
const money = value => new Intl.NumberFormat("en-GB", {style:"currency", currency:"GBP"}).format(Number(value || 0));
const date = value => value ? new Intl.DateTimeFormat("en-GB", {day:"numeric", month:"long", year:"numeric"}).format(new Date(value.slice(0,10) + "T12:00:00")) : "To be confirmed";

async function api(path, options = {}) {
  const response = await fetch(path, {headers:{"Content-Type":"application/json"}, ...options});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(Array.isArray(body.detail) ? body.detail.map(x => x.msg).join(", ") : body.detail || "Something went wrong");
  return body;
}
function toast(text) {
  $("#toast").textContent = text;
  $("#toast").classList.remove("hidden");
  setTimeout(() => $("#toast").classList.add("hidden"), 3200);
}
function existing(type) { return data.submissions.find(x => x.form_type === type)?.data || {}; }
function bookingJourneyUnlocked() {
  return data.record.kind !== "wedding" || Boolean(data.quote) || !["enquiry", "quoted"].includes(data.record.status);
}
function completed() {
  const booking = existing("booking_form"), final = existing("final_questionnaire");
  return {
    quote: Boolean(data.quote),
    invoices: Boolean(data.invoices.length),
    booking: Boolean(data.submissions.some(x => x.form_type === "booking_form")),
    final: Boolean(data.submissions.some(x => x.form_type === "final_questionnaire")),
    agreement: Boolean(data.contract),
  };
}
function countdown() {
  if (!data.record.event_date) return "Date to be confirmed";
  const today = new Date(); today.setHours(0,0,0,0);
  const event = new Date(data.record.event_date + "T12:00:00");
  const days = Math.ceil((event - today) / 86400000);
  if (days > 1) return `<b>${days}</b> days to go`;
  if (days === 1) return "<b>1</b> day to go";
  if (days === 0) return "Today's the day!";
  return "Your wonderful day";
}
function directionsUrl() {
  const r = data.record;
  if (r.venue_place_id) return `https://www.google.com/maps/dir/?api=1&destination_place_id=${encodeURIComponent(r.venue_place_id)}&destination=${encodeURIComponent(r.venue_address || r.venue_or_project || "Wedding venue")}`;
  if (r.venue_lat != null && r.venue_lng != null) return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(`${r.venue_lat},${r.venue_lng}`)}`;
  if (r.venue_address || r.venue_or_project) return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(r.venue_address || r.venue_or_project)}`;
  return "";
}

async function init() {
  try {
    data = await api(`/api/client/${token}`);
    if (!bookingJourneyUnlocked() && !["Overview", "Choose package"].includes(active)) active = "Overview";
    if (active === "Final details" && !data.final_details_unlocked) active = "Overview";
    const brand = data.business.brand || (data.record.kind === "wedding" ? "wbm" : "ivory");
    document.body.classList.add(`brand-${brand}`);
    $("#business-logo").src = brand === "ivory" ? "/static/branding/ivory-digital-logo.png" : "/static/branding/weddings-by-mark-logo.png";
    $("#business-logo").alt = data.business.name;
    $("#business-name").textContent = data.business.name;
    $("#business-email").textContent = data.business.email || `Contact ${data.business.name}`;
    $("#business-email").href = data.business.email ? `mailto:${data.business.email}` : "#";
    $("#booking-label").textContent = data.record.kind === "wedding" ? "YOUR WEDDING BOOKING" : "YOUR DIGITAL PROJECT";
    $("#record-title").textContent = data.record.title;
    $("#record-summary").textContent = `${date(data.record.event_date)} · ${data.record.venue_or_project || "Details to be confirmed"}`;
    $("#countdown").innerHTML = data.record.kind === "wedding" ? countdown() : "Your project space";
    $("#loading").classList.add("hidden");
    $("#portal").classList.remove("hidden");
    renderTabs();
    render();
  } catch (error) {
    $("#loading").classList.add("hidden");
    $("#error").classList.remove("hidden");
    $("#error-message").textContent = error.message;
  }
}

function tabDefinition() {
  const done = completed();
  const hasQuote = data.record.kind === "wedding" && data.catalog.packages.length;
  const unlocked = bookingJourneyUnlocked();
  return [
    {name:"Overview", icon:"⌂"},
    ...(hasQuote ? [{name:"Choose package", icon:"♡", done:done.quote}] : []),
    ...(unlocked ? [{name:"Invoices", icon:"£", done:done.invoices},
      {name:"Booking form", icon:"✎", done:done.booking},
      ...(data.record.kind === "wedding" ? [{name:"Final details", icon:"☷", done:done.final, locked:!data.final_details_unlocked}] : []),
      ...(data.documents?.length ? [{name:"Documents", icon:"▤"}] : []),
      {name:"Agreement", icon:"✓", done:done.agreement}] : []),
  ];
}
function setActive(tab) {
  if (tab === "Final details" && !data.final_details_unlocked) {
    toast("Final wedding details open 30 days before your wedding");
    return;
  }
  active = tab;
  window.scrollTo({top:Math.max(0, $("#tabs").offsetTop - 10), behavior:"smooth"});
  renderTabs();
  render();
}
function renderTabs() {
  $("#tabs").innerHTML = tabDefinition().map(tab => `<button class="${tab.name === active ? "active" : ""} ${tab.locked?"locked":""}" data-tab="${tab.name}" ${tab.locked?"aria-disabled=\"true\"":""}><span class="tab-icon">${tab.locked?"🔒":tab.icon}</span><span>${tab.name}</span>${tab.done ? `<i class="tab-check">✓</i>` : ""}</button>`).join("");
  document.querySelectorAll("[data-tab]").forEach(button => button.onclick = () => setActive(button.dataset.tab));
}
function render() {
  if (active === "Overview") overview();
  else if (active === "Choose package") quotePanel();
  else if (active === "Invoices") invoicesPanel();
  else if (active === "Booking form") bookingForm();
  else if (active === "Final details") finalForm();
  else if (active === "Documents") documentsPanel();
  else agreement();
}

function overview() {
  const done = completed();
  const unlocked = bookingJourneyUnlocked();
  const journey = data.record.kind === "wedding" && !unlocked
    ? [["Choose package", "Package quote", done.quote]]
    : data.record.kind === "wedding" ? [
    ["Choose package", "Package quote", done.quote], ["Booking form", "Booking form", done.booking],
    ["Agreement", "Agreement", done.agreement], ["Final details", "Final details", done.final, !data.final_details_unlocked]
  ] : [["Booking form", "Project information", done.booking], ["Agreement", "Agreement", done.agreement]];
  const next = journey.find(item => !item[2] && !item[3]);
  const directions = directionsUrl();
  const welcomeText = unlocked ? "Your invoice, Wedding Booking Form/questionnaire and contract are all kept safely together here. You can return using the same secure link whenever you need to." : "Your enquiry has been received and your secure wedding area is ready. Your package choices will appear here as soon as Mark sends your quote.";
  $("#panel").innerHTML = `<div class="welcome-grid"><article class="welcome-card"><small>WELCOME TO YOUR SECURE AREA</small><h2>Hello ${esc(data.record.client.first_name)}, everything is in one place.</h2><p>${welcomeText}</p>${next ? `<div class="next-step"><span><strong>Your next step</strong><small>${esc(next[1])} is ready when you are.</small></span><button data-go="${esc(next[0])}">Continue</button></div>` : `<div class="complete">Everything currently requested has been completed - thank you!</div>`}</article><aside class="venue-card"><small>${data.record.kind === "wedding" ? "YOUR WEDDING VENUE" : "YOUR PROJECT"}</small><strong>${esc(data.record.venue_or_project || "Details to be confirmed")}</strong><span>${esc(data.record.venue_address || (data.record.kind === "wedding" ? "The full address will appear here once confirmed." : data.record.package_name || ""))}</span>${directions ? `<a href="${esc(directions)}" target="_blank" rel="noopener">Open directions in Google Maps ↗</a>` : ""}</aside></div><div class="journey">${journey.map((item,index) => `<button class="${item[2] ? "done" : ""} ${item[3]?"locked":""}" data-go="${esc(item[0])}"><i>${item[2] ? "✓" : item[3]?"🔒":index + 1}</i><span><strong>${esc(item[1])}</strong><small>${item[2] ? "Completed" : item[3]?"Opens 30 days before your wedding":"Waiting for you"}</small></span></button>`).join("")}</div><div class="summary"><div><small>PACKAGE / SERVICE</small><strong>${esc(data.record.package_name || "To be confirmed")}</strong></div><div><small>TOTAL</small><strong>${money(data.record.quoted_total)}</strong></div><div><small>BOOKING FEE / DEPOSIT</small><strong>${money(data.record.deposit_amount)}</strong></div></div>`;
  document.querySelectorAll("[data-go]").forEach(button => button.onclick = () => setActive(button.dataset.go));
}

function quotePanel() {
  if (data.quote) {
    const invoice = data.invoices.find(item => item.id === data.quote.invoice_id) || data.invoices[0];
    $("#panel").innerHTML = `<h2>Your package is confirmed</h2><p class="intro">Your selection has been saved and ${data.quote.invoice_number ? `invoice ${esc(data.quote.invoice_number)}` : "your invoice"} has been created.</p><div class="complete">✓ Accepted on ${date(data.quote.accepted_at)}</div><div class="quote-lines">${data.quote.line_items.map(item => `<div><span><strong>${esc(item.name)}</strong><small>${item.type === "addon" ? "Optional add-on" : "Wedding package"}</small></span><b>${money(item.total)}</b></div>`).join("")}</div><div class="quote-total"><span><small>Total</small><strong>${money(data.quote.total)}</strong></span><span><small>Booking fee</small><strong>${money(data.quote.deposit_amount)}</strong>${invoice?.deposit_due_date ? `<em>Due ${date(invoice.deposit_due_date)}</em>` : ""}</span>${invoice?.due_date ? `<span><small>Remaining balance</small><strong>${money(Number(data.quote.total) - Number(data.quote.deposit_amount))}</strong><em>Due ${date(invoice.due_date)}</em></span>` : ""}</div><div class="actions"><button class="primary" data-open-invoices>View your invoice</button></div>`;
    $("[data-open-invoices]").onclick = () => setActive("Invoices");
    return;
  }
  const packages = data.catalog.packages;
  $("#panel").innerHTML = `<h2>Choose your wedding package</h2><p class="intro">You can choose a different package from the one mentioned on your enquiry. Select one package, add any extras and check the live total before accepting.</p><form id="quote-form"><div class="package-grid">${packages.map((item,index) => `<label class="package-card"><input type="radio" name="package_id" value="${item.id}" ${index === 0 ? "checked" : ""}><span class="package-check">✓</span><span class="package-name"><strong>${esc(item.name)}</strong><b>${money(item.price)}</b></span><small>${esc(item.description)}</small><em>${money(item.deposit_amount)} booking fee · due within one day of accepting</em></label>`).join("")}</div><section class="addon-section"><h3>Optional add-ons</h3><p>Only extras available for your selected package are shown.</p><div id="addon-list"></div></section><div class="quote-footer"><div><small>TOTAL</small><strong id="quote-total">£0.00</strong><span id="quote-deposit"></span></div><label class="quote-confirm"><input type="checkbox" name="confirmed" required><span>I confirm that this package, the selected add-ons and the total shown are correct.</span></label><button class="primary" type="submit">Accept package & create invoice</button></div></form>`;
  document.querySelectorAll('input[name="package_id"]').forEach(input => input.onchange = renderAddons);
  $("#quote-form").onsubmit = acceptSelectedQuote;
  renderAddons();
}

function invoicesPanel() {
  if (!data.invoices.length) {
    $("#panel").innerHTML = `<h2>Your invoices</h2><p class="intro">Your invoice will appear here automatically after you accept your package or service quote.</p><div class="invoice-empty"><strong>No invoice yet</strong><span>Choose and accept your package first - there is nothing else you need to do.</span></div>`;
    return;
  }
  $("#panel").innerHTML = `<h2>Your invoices & payments</h2><p class="intro">Download your invoice for the bank-transfer details and use the current invoice number as your payment reference.</p><div class="client-invoices">${data.invoices.map(invoice => `<article class="client-invoice"><header><div><span><strong>${esc(invoice.number)}</strong>${invoice.legacy_number?`<small class="client-legacy-ref">Previously ${esc(invoice.legacy_number)} in Studio Ninja</small>`:""}</span><span class="invoice-status ${invoice.status}">${esc(String(invoice.status).replaceAll("_"," "))}</span></div><b>${money(invoice.total)}</b></header>${invoice.line_items?.length ? `<div class="client-invoice-lines">${invoice.line_items.map(item => `<div><span><b>${esc(item.name)}</b>${item.description ? `<small>${esc(item.description)}</small>` : ""}</span><strong>${money(item.total)}</strong></div>`).join("")}</div>` : invoice.description ? `<div class="client-invoice-lines"><div><span><b>${esc(invoice.description)}</b></span><strong>${money(invoice.total)}</strong></div></div>` : ""}${invoice.payment_schedule?.length?`<section class="client-payment-schedule"><strong>Original payment schedule</strong>${invoice.payment_schedule.map(item=>`<div><span>${esc(item.label||"Scheduled payment")}<small>${item.due_date?date(item.due_date):"No due date recorded"} · ${esc(String(item.status||"scheduled").replaceAll("_"," "))}</small></span><b>${money(item.amount)}</b></div>`).join("")}</section>`:""}<dl><dt>Issued</dt><dd>${date(invoice.issue_date)}</dd>${!invoice.payment_schedule?.length&&invoice.deposit_due_date ? `<dt>Booking fee</dt><dd>${money(invoice.deposit_amount)} · due ${date(invoice.deposit_due_date)}</dd>` : ""}${!invoice.payment_schedule?.length&&invoice.due_date ? `<dt>Remaining balance</dt><dd>${money(Math.max(0,Number(invoice.total)-Number(invoice.deposit_amount||0)))} · due ${date(invoice.due_date)}</dd>` : ""}<dt>Paid so far</dt><dd>${money(invoice.paid)}</dd><dt><strong>Total outstanding</strong></dt><dd><strong>${money(invoice.balance)}</strong></dd></dl><div class="client-invoice-actions"><a class="primary" href="/api/client/${token}/invoices/${invoice.id}/invoice.pdf">Download invoice PDF</a>${invoice.paid > 0 ? `<a class="secondary-client" href="/api/client/${token}/invoices/${invoice.id}/receipt.pdf">Download receipt</a>` : ""}</div></article>`).join("")}</div>`;
}

function documentsPanel() {
  const documents = data.documents || [];
  $("#panel").innerHTML = `<h2>Your original documents</h2><p class="intro">These are the original files retained from your previous booking record. Your current invoice and receipt remain in the Invoices section.</p><div class="client-documents">${documents.map(document => `<article><i>▤</i><span><strong>${esc(document.original_name)}</strong><small>${esc(String(document.legacy_document_type||document.category||"document").replaceAll("_"," "))}${document.document_date?` · ${date(document.document_date)}`:""}</small></span><a class="secondary-client" href="/api/client/${token}/documents/${document.id}">Download</a></article>`).join("")||`<div class="invoice-empty"><strong>No documents available</strong><span>Any files shared with you will appear here.</span></div>`}</div>`;
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
  const addonTotal = data.catalog.addons.filter(x => selectedIds.includes(x.id)).reduce((sum,x) => sum + Number(x.price),0);
  $("#quote-total").textContent = money(Number(selected.price) + addonTotal);
  $("#quote-deposit").textContent = `${money(selected.deposit_amount)} booking fee due within one day of accepting`;
}
async function acceptSelectedQuote(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  if (!confirm("Accept this package and create the invoice? Please check the package and add-ons shown first.")) return;
  try {
    await api(`/api/client/${token}/quote`, {method:"POST", body:JSON.stringify({package_id:form.get("package_id"), addon_ids:form.getAll("addon_id"), confirmed:form.get("confirmed") === "on"})});
    data = await api(`/api/client/${token}`);
    toast("Package accepted and invoice created");
    setActive("Invoices");
  } catch (error) { toast(error.message); }
}

function field(label, name, value = "", full = false, type = "text", required = false) {
  return `<label class="${full ? "full" : ""}">${label}${required ? " *" : ""}<input name="${name}" type="${type}" value="${esc(value)}" ${required ? "required" : ""}></label>`;
}
function bookingForm() {
  const x = existing("booking_form"), wedding = data.record.kind === "wedding";
  if (!wedding) {
    $("#panel").innerHTML = `<h2>Project information</h2><p class="intro">Please check and complete the details below.</p>${x.contact_phone ? `<div class="complete">✓ Previously submitted - you can update it below.</div><br>` : ""}<form id="booking-form"><div class="form-grid">${field("Your full name","full_name",x.full_name||`${data.record.client.first_name} ${data.record.client.last_name||""}`,false,"text",true)}${field("Company name","partner_or_company",x.partner_or_company||data.record.client.company_name||"")}${field("Contact telephone","contact_phone",x.contact_phone||data.record.client.phone||"")}${field("Address","address",x.address||data.record.client.address||"",true)}${field("Project/service required","service_required",x.service_required||data.record.package_name||"",true)}${field("Current website","current_website",x.current_website||"")}${field("Preferred completion date","target_date",x.target_date||data.record.event_date||"",false,"date")}<label class="full">Anything else we should know?<textarea name="additional_notes" rows="4">${esc(x.additional_notes||"")}</textarea></label></div><div class="actions"><button class="primary" type="submit">Save project information</button></div></form>`;
    $("#booking-form").onsubmit = event => submitForm(event,"booking_form");
    return;
  }
  const venueName = data.record.venue_or_project || "", venueAddress = data.record.venue_address || "";
  $("#panel").innerHTML = `<h2>Wedding Booking Form</h2><p class="intro">This is split into three short steps and saves everything securely against your wedding.</p>${x.primary_full_name ? `<div class="complete">✓ Previously submitted - you can update it below.</div><br>` : ""}<form id="booking-form"><div class="form-progress"><span></span><span></span><span></span></div>
    <section class="form-step" data-step="0"><h3>1. About you both</h3><p class="step-intro">Your names and contact details.</p><div class="form-grid">${field("Bride's/Groom's full name","primary_full_name",x.primary_full_name||`${data.record.client.first_name} ${data.record.client.last_name||""}`,false,"text",true)}${field("Bride's/Groom's phone number","primary_phone",x.primary_phone||data.record.client.phone||"",false,"tel",true)}${field("Bride's/Groom's email","primary_email",x.primary_email||data.record.client.email,false,"email",true)}${field("Groom's/Bride's full name","partner_full_name",x.partner_full_name||data.record.client.partner_name||"",false,"text",true)}${field("Groom's/Bride's phone number","partner_phone",x.partner_phone||"",false,"tel",true)}${field("Groom's/Bride's email","partner_email",x.partner_email||"",false,"email")}${field("Street address","street_address",x.street_address||data.record.client.address||"",true,"text",true)}${field("Town","town",x.town||"",false,"text",true)}${field("City/County","county",x.county||"",false,"text",true)}${field("Postcode","postcode",x.postcode||"",false,"text",true)}</div></section>
    <section class="form-step" data-step="1"><h3>2. Your wedding day</h3><p class="step-intro">Confirm the date, venue and ceremony details.</p><div class="form-grid">${field("Date of wedding/event","wedding_date",x.wedding_date||data.record.event_date||"",false,"date",true)}${field("Ceremony/service time","ceremony_time",x.ceremony_time||"",false,"time",true)}<input name="venue_name" type="hidden" value="${esc(venueName)}"><input name="venue_address" type="hidden" value="${esc(venueAddress)}"><input name="venue_place_id" type="hidden" value="${esc(data.record.venue_place_id||"")}"><input name="venue_lat" type="hidden" value="${esc(data.record.venue_lat??"")}"><input name="venue_lng" type="hidden" value="${esc(data.record.venue_lng??"")}"><label class="full">Wedding venue<input value="${esc(venueName)}${venueAddress&&venueAddress!==venueName?` - ${esc(venueAddress)}`:""}" readonly></label><label class="full">Exact ceremony details and venue(s) *<textarea name="ceremony_details" rows="4" required>${esc(x.ceremony_details||venueAddress||venueName)}</textarea></label><label class="full">Exact reception venue details *<textarea name="reception_details" rows="4" required placeholder="If this is the same as the ceremony venue, please say so">${esc(x.reception_details||"")}</textarea></label></div></section>
    <section class="form-step" data-step="2"><h3>3. Package and planning</h3><p class="step-intro">A few final details to help plan everything perfectly.</p><div class="form-grid">${data.quote ? `<label class="full">Package selected<input name="package_selected" value="${esc(data.record.package_name)}" readonly></label>` : `<label class="full">Package selected<select name="package_selected" required><option value="">Please choose</option>${data.catalog.packages.map(p => `<option value="${esc(p.name)}" ${(x.package_selected||data.record.package_name)===p.name?"selected":""}>${esc(p.name)} - ${money(p.price)}</option>`).join("")}</select></label>`}<fieldset class="full form-options"><legend>Payment schedule</legend><strong>Simple bank-transfer payments</strong><span>Your booking fee is due within one day of accepting your quote. The remaining balance is due 45 days before your wedding.</span></fieldset>${field("How many people will be in your wedding party?","wedding_party_size",x.wedding_party_size||"",false,"number",true)}<label class="full">Are there any unique events happening that I need to know about? *<textarea name="unique_events" rows="4" required placeholder="For example, the bride will arrive on a horse">${esc(x.unique_events||"")}</textarea></label><label class="full">Wedding guest photo uploads - Package 2 and upwards<select name="guest_uploads"><option value="">Please choose</option><option value="yes" ${x.guest_uploads==="yes"?"selected":""}>Yes please</option><option value="no" ${x.guest_uploads==="no"?"selected":""}>No thank you</option></select></label><label class="full">Additional information<textarea name="additional_information" rows="4">${esc(x.additional_information||"")}</textarea></label><label class="full">Highlight video music choices for Gold, Platinum and Ultimate<textarea name="highlight_music" rows="4" placeholder="Please give two songs">${esc(x.highlight_music||"")}</textarea></label></div></section>
    <div class="form-step-actions"><button id="booking-back" class="secondary-client" type="button">Back</button><button id="booking-next" class="primary" type="button">Continue</button><button id="booking-save" class="primary" type="submit">Save Wedding Booking Form</button></div></form>`;
  $("#booking-form").onsubmit = event => submitForm(event,"booking_form");
  wireBookingSteps();
}
function wireBookingSteps() {
  const steps = [...document.querySelectorAll(".form-step")], bars = [...document.querySelectorAll(".form-progress span")];
  const show = () => {
    steps.forEach((step,index) => step.classList.toggle("active",index === bookingStep));
    bars.forEach((bar,index) => {bar.className = index < bookingStep ? "done" : index === bookingStep ? "active" : ""});
    $("#booking-back").classList.toggle("hidden",bookingStep === 0);
    $("#booking-next").classList.toggle("hidden",bookingStep === steps.length - 1);
    $("#booking-save").classList.toggle("hidden",bookingStep !== steps.length - 1);
  };
  $("#booking-back").onclick = () => {bookingStep = Math.max(0,bookingStep-1);show()};
  $("#booking-next").onclick = () => {
    const invalid = [...steps[bookingStep].querySelectorAll("input,select,textarea")].find(input => !input.checkValidity());
    if (invalid) { invalid.reportValidity(); return; }
    bookingStep = Math.min(steps.length-1,bookingStep+1); show(); window.scrollTo({top:$("#panel").offsetTop-10,behavior:"smooth"});
  };
  show();
}
function finalForm() {
  if (!data.final_details_unlocked) {
    $("#panel").innerHTML = `<h2>Final wedding details</h2><div class="final-details-locked"><i>🔒</i><strong>This section opens 30 days before your wedding</strong><span>It keeps the last timings and supplier information up to date. Mark can also open it early if needed.</span><button class="secondary-client" data-return-overview>Return to overview</button></div>`;
    $("[data-return-overview]").onclick = () => setActive("Overview");
    return;
  }
  const x = existing("final_questionnaire");
  $("#panel").innerHTML = `<h2>Final wedding details</h2><p class="intro">Please give as much detail as possible so the day runs smoothly.</p>${x.timeline ? `<div class="complete">✓ Previously submitted - you can update it below.</div><br>` : ""}<form id="final-form"><div class="form-grid"><label class="full">Full timeline for the day *<textarea name="timeline" rows="6" required>${esc(x.timeline||"")}</textarea></label><label class="full">Important family/group photographs<textarea name="group_photos" rows="4">${esc(x.group_photos||"")}</textarea></label><label class="full">Supplier names and contact details<textarea name="suppliers" rows="4">${esc(x.suppliers||"")}</textarea></label>${field("Speeches planned for","speeches_time",x.speeches_time||"")}${field("First dance time","first_dance_time",x.first_dance_time||"")}<label class="full">Surprises, sensitivities or special requests<textarea name="special_requests" rows="4">${esc(x.special_requests||"")}</textarea></label><label class="full">Video music suggestions, if included<textarea name="music_suggestions" rows="3">${esc(x.music_suggestions||"")}</textarea></label></div><div class="actions"><button class="primary" type="submit">Save final details</button></div></form>`;
  $("#final-form").onsubmit = event => submitForm(event,"final_questionnaire");
}
async function submitForm(event, type) {
  event.preventDefault();
  const form = new FormData(event.currentTarget), values = {};
  for (const [key,value] of form.entries()) values[key] = String(value).trim();
  if (type === "booking_form" && data.record.kind === "wedding") values.payment_options = ["Booking fee due within one day of accepting the quote; remaining balance due 45 days before the wedding"];
  try {
    await api(`/api/client/${token}/forms`, {method:"POST", body:JSON.stringify({form_type:type,data:values})});
    data = await api(`/api/client/${token}`);
    toast("Your details have been saved");
    bookingStep = 0;
    renderTabs(); render();
  } catch (error) { toast(error.message); }
}
function agreement() {
  const contract = data.contract_template;
  if (!contract) { $("#panel").innerHTML = `<h2>Agreement unavailable</h2><p class="intro">Please contact ${esc(data.business.name)}.</p>`; return; }
  if (data.contract) {
    const imported = data.contract.is_legacy_import;
    $("#panel").innerHTML = `<h2>Agreement accepted</h2><div class="complete">✓ ${imported?"Original acceptance recorded for":"Accepted by"} ${esc(data.contract.accepted_name)} on ${date(data.contract.accepted_at)}. Version ${esc(data.contract.version)}.</div>${imported?`<div class="legacy-contract-note"><strong>Imported from your Studio Ninja booking</strong><span>${esc(data.contract.source_detail||"The original signed contract is retained in your Documents section.")}</span>${data.documents?.some(x=>x.legacy_document_type==="contract")?`<button class="secondary-client" data-open-documents>View original document</button>`:""}</div>`:`<div class="contract" style="margin-top:16px">${esc(contract.body)}</div>`}`;
    if ($("[data-open-documents]")) $("[data-open-documents]").onclick = () => setActive("Documents");
    return;
  }
  $("#panel").innerHTML = `<h2>${esc(contract.title)}</h2><p class="intro">Version ${esc(contract.version)}. Please read the complete agreement before accepting it.</p><div class="contract">${esc(contract.body)}</div><form id="contract-form"><div class="form-grid" style="margin-top:17px">${field("Your full legal name","accepted_name",`${data.record.client.first_name} ${data.record.client.last_name||""}`,false,"text",true)}${field("Your booking email","accepted_email",data.record.client.email,false,"email",true)}</div><label class="agreement"><input name="agreed" type="checkbox" required><span>I have read and agree to the complete booking agreement above. I understand this electronic acceptance will be recorded with the date and technical audit information.</span></label><div class="actions"><button class="primary" type="submit">Accept agreement</button></div></form>`;
  $("#contract-form").onsubmit = async event => {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try {
      await api(`/api/client/${token}/contract`, {method:"POST", body:JSON.stringify({accepted_name:form.get("accepted_name"),accepted_email:form.get("accepted_email"),agreed:form.get("agreed") === "on"})});
      data = await api(`/api/client/${token}`); toast("Agreement accepted"); renderTabs(); render();
    } catch (error) { toast(error.message); }
  };
}

init();
