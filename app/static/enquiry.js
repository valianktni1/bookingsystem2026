const form = document.querySelector("#enquiry-form");
const fieldHost = document.querySelector("#enquiry-fields");
const errorBox = document.querySelector("#form-error");
const submitButton = document.querySelector("#submit-button");
let formConfig = null;

function tellParentHeight() {
  const height = Math.ceil(document.documentElement.scrollHeight);
  window.parent.postMessage({type: "wbm-enquiry-height", height}, "*");
}
new ResizeObserver(tellParentHeight).observe(document.documentElement);
window.addEventListener("load", tellParentHeight);

function money(value) {
  return new Intl.NumberFormat("en-GB", {style: "currency", currency: "GBP", maximumFractionDigits: 0}).format(Number(value || 0));
}

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function addCommonInputSettings(input, field) {
  input.name = field.key;
  input.required = Boolean(field.required);
  input.placeholder = field.placeholder || "";
  input.dataset.custom = field.custom ? "true" : "false";
  if (["primary_first_name", "partner_first_name"].includes(field.key)) input.maxLength = 100;
  else if (field.key === "email") input.maxLength = 254;
  else if (field.key === "message" || field.custom) input.maxLength = 5000;
  else input.maxLength = 240;
}

function renderVenue(field, label) {
  label.classList.add("venue-label");
  const hidden = [
    ["enquiry-venue-name", "location"], ["enquiry-venue-address", "venue_address"],
    ["enquiry-venue-place-id", "venue_place_id"], ["enquiry-venue-lat", "venue_lat"],
    ["enquiry-venue-lng", "venue_lng"],
  ];
  hidden.forEach(([id, name]) => {
    const input = element("input"); input.id = id; input.name = name; input.type = "hidden"; label.append(input);
  });
  const picker = element("div", "venue-picker"); picker.id = "enquiry-venue-picker"; label.append(picker);
  const manual = element("input", "venue-manual"); manual.id = "enquiry-venue-manual"; manual.maxLength = 240; manual.placeholder = "Enter your venue or location manually"; manual.hidden = true; label.append(manual);
  const summary = element("div", "venue-summary"); summary.id = "enquiry-venue-summary"; summary.append(element("span", "", "No venue selected yet")); label.append(summary);
  const toggle = element("button", "venue-manual-toggle", "Can't find it? Enter the venue manually"); toggle.id = "enquiry-venue-manual-toggle"; toggle.type = "button"; label.append(toggle);
}

function renderField(field) {
  const label = element("label", field.width === "full" ? "full" : "");
  if (field.field_type === "checkbox") {
    label.classList.add("privacy");
    const input = element("input"); input.type = "checkbox"; addCommonInputSettings(input, field);
    label.append(input, element("span", "", `${field.label}${field.required ? " *" : ""}`));
    if (field.help_text) label.append(element("small", "counter", field.help_text));
    return label;
  }
  label.append(document.createTextNode(`${field.label}${field.required ? " *" : ""}`));
  if (field.field_type === "venue") {
    renderVenue(field, label);
  } else if (field.field_type === "textarea") {
    const input = element("textarea"); input.rows = 5; addCommonInputSettings(input, field); label.append(input);
  } else if (field.field_type === "select" || field.field_type === "package") {
    const input = element("select"); addCommonInputSettings(input, field);
    if (field.field_type === "package") input.id = "package-interest";
    const blank = element("option", "", field.placeholder || "Please choose"); blank.value = ""; input.append(blank);
    (field.options || []).forEach(option => { const item = element("option", "", option); item.value = option; input.append(item); });
    label.append(input);
  } else {
    const input = element("input"); input.type = field.field_type; addCommonInputSettings(input, field);
    if (field.key === "primary_first_name") input.autocomplete = "given-name";
    if (field.key === "email") input.autocomplete = "email";
    if (field.key === "phone") input.autocomplete = "tel";
    label.append(input);
  }
  if (field.help_text) label.append(element("small", "counter", field.help_text));
  return label;
}

async function loadPackages() {
  const select = document.querySelector("#package-interest");
  if (!select) return;
  try {
    const response = await fetch("/api/public/catalog");
    const data = await response.json();
    data.packages.forEach(item => {
      const option = element("option", "", `${item.name} - ${money(item.price)}`);
      option.value = item.name;
      select.append(option);
    });
  } catch (_) { /* The form remains usable if the catalogue is temporarily unavailable. */ }
}

function attachVenue() {
  if (!document.querySelector("#enquiry-venue-picker")) return;
  window.WBMVenues?.attach({
    host: "#enquiry-venue-picker", manual: "#enquiry-venue-manual",
    manualToggle: "#enquiry-venue-manual-toggle", summary: "#enquiry-venue-summary",
    name: "#enquiry-venue-name", address: "#enquiry-venue-address",
    placeId: "#enquiry-venue-place-id", lat: "#enquiry-venue-lat", lng: "#enquiry-venue-lng",
    required: true, placeholder: formConfig.fields.find(field => field.key === "location")?.placeholder || "Start typing your wedding venue",
  });
}

async function initialiseForm() {
  try {
    const response = await fetch("/api/public/enquiry-form");
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "The enquiry form could not be loaded");
    formConfig = body;
    document.querySelector("#enquiry-heading").textContent = body.heading;
    document.querySelector("#enquiry-introduction").textContent = body.introduction;
    document.querySelector("#success-heading").textContent = body.success_heading;
    document.querySelector("#success-message").textContent = body.success_message;
    submitButton.textContent = body.submit_label;
    const payment = document.querySelector("#payment-note");
    payment.replaceChildren();
    if (body.payment_title || body.payment_options.length) {
      if (body.payment_title) payment.append(element("strong", "", body.payment_title));
      body.payment_options.forEach(option => payment.append(element("div", "payment-option", option)));
      payment.classList.remove("hidden");
    }
    fieldHost.replaceChildren(...body.fields.map(renderField));
    await loadPackages();
    attachVenue();
    submitButton.disabled = false;
    tellParentHeight();
  } catch (error) {
    fieldHost.replaceChildren(element("p", "error", error.message));
    errorBox.textContent = "Please refresh the page or contact Mark directly.";
  }
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (!formConfig) return;
  errorBox.textContent = "";
  submitButton.disabled = true;
  const originalLabel = formConfig.submit_label;
  submitButton.textContent = "Sending…";
  const raw = new FormData(form);
  const values = Object.fromEntries(raw.entries());
  const customAnswers = {};
  formConfig.fields.filter(field => field.custom).forEach(field => {
    customAnswers[field.key] = field.field_type === "checkbox" ? raw.has(field.key) : (values[field.key] ?? null);
    delete values[field.key];
  });
  values.custom_answers = customAnswers;
  if (!String(values.location || "").trim()) {
    errorBox.textContent = "Please choose your wedding venue or enter it manually.";
    submitButton.disabled = false; submitButton.textContent = originalLabel; return;
  }
  values.privacy_agreed = raw.has("privacy_agreed");
  for (const key of ["venue_lat", "venue_lng"]) if (values[key] !== "" && values[key] != null) values[key] = Number(values[key]);
  for (const key of Object.keys(values)) if (values[key] === "") values[key] = null;
  try {
    const response = await fetch("/api/public/enquiries", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(values)});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(Array.isArray(body.detail) ? body.detail.map(item => item.msg).join(", ") : body.detail || "Your enquiry could not be sent");
    document.querySelector("#enquiry-card").classList.add("hidden");
    document.querySelector("#success").classList.remove("hidden");
    window.scrollTo({top: 0, behavior: "smooth"});
    tellParentHeight();
  } catch (error) {
    errorBox.textContent = error.message;
    submitButton.disabled = false;
    submitButton.textContent = originalLabel;
    tellParentHeight();
  }
});

initialiseForm();
