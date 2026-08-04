const form = document.querySelector("#enquiry-form");
const errorBox = document.querySelector("#form-error");
const submitButton = document.querySelector("#submit-button");

function tellParentHeight() {
  const height = Math.ceil(document.documentElement.scrollHeight);
  window.parent.postMessage({type: "wbm-enquiry-height", height}, "*");
}
new ResizeObserver(tellParentHeight).observe(document.documentElement);
window.addEventListener("load", tellParentHeight);

async function loadPackages() {
  try {
    const response = await fetch("/api/public/catalog");
    const data = await response.json();
    const select = document.querySelector("#package-interest");
    data.packages.forEach(item => select.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)} - ${money(item.price)}</option>`));
  } catch (_) { /* The form remains usable if the catalogue is temporarily unavailable. */ }
}
function escapeHtml(value) {
  return String(value || "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}
function money(value) { return new Intl.NumberFormat("en-GB", {style:"currency", currency:"GBP", maximumFractionDigits:0}).format(Number(value || 0)); }

form.addEventListener("submit", async event => {
  event.preventDefault();
  errorBox.textContent = "";
  submitButton.disabled = true;
  submitButton.textContent = "Sending…";
  const values = Object.fromEntries(new FormData(form).entries());
  if (!String(values.location || "").trim()) {
    errorBox.textContent = "Please choose your wedding venue or enter it manually.";
    submitButton.disabled = false;
    submitButton.textContent = "Submit enquiry";
    return;
  }
  values.privacy_agreed = values.privacy_agreed === "on";
  for (const key of ["venue_lat", "venue_lng"]) if (values[key] !== "") values[key] = Number(values[key]);
  for (const key of Object.keys(values)) if (values[key] === "") values[key] = null;
  try {
    const response = await fetch("/api/public/enquiries", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(values)});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(Array.isArray(body.detail) ? body.detail.map(x => x.msg).join(", ") : body.detail || "Your enquiry could not be sent");
    document.querySelector("#enquiry-card").classList.add("hidden");
    document.querySelector("#success").classList.remove("hidden");
    window.scrollTo({top:0, behavior:"smooth"});
    tellParentHeight();
  } catch (error) {
    errorBox.textContent = error.message;
    submitButton.disabled = false;
    submitButton.textContent = "Submit enquiry";
    tellParentHeight();
  }
});

loadPackages();
window.addEventListener("load", () => window.WBMVenues?.attach({
  host: "#enquiry-venue-picker",
  manual: "#enquiry-venue-manual",
  manualToggle: "#enquiry-venue-manual-toggle",
  summary: "#enquiry-venue-summary",
  name: "#enquiry-venue-name",
  address: "#enquiry-venue-address",
  placeId: "#enquiry-venue-place-id",
  lat: "#enquiry-venue-lat",
  lng: "#enquiry-venue-lng",
  required: true,
  placeholder: "Start typing your wedding venue",
}));
