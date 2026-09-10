import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_v844_assets_load_last_and_define_one_workspace_contract():
    index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/v844.js").read_text(encoding="utf-8")
    legacy_workspace = (ROOT / "app/static/v895.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/v844.css").read_text(encoding="utf-8")

    assert "/static/v844.css?v=workspace-foundation-v8-44" in index
    assert "/static/v844.js?v=journey-quote-routing-v8-45-2" in index
    assert "/static/v895.js?v=journey-quote-routing-v8-45-2" in index
    assert "/static/v895.js?v=journey-quote-routing-v8-45-2" in index
    assert index.rfind("/static/v844.js") > index.rfind("/static/v835.js")
    assert "one authoritative booking-workspace navigation controller" in script
    assert 'else if (selected === "Emails") renderBookingEmails(record, body);' in script
    assert 'else if (selected === "Payments") renderFinance(record, body);' in script
    assert 'else if (selected === "Files") renderRecordDocuments(record, body);' in script
    assert "renderJourneyV844" in script
    assert "renderFormsAndAgreement: renderFormsAndAgreementV895" in legacy_workspace
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in css


def test_v844_runtime_routes_each_visible_tab_to_the_correct_renderer():
    script_path = ROOT / "app/static/v844.js"
    node_test = r"""
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const calls = [];
const quoteHost = {innerHTML: ""};
const formsHost = {innerHTML: ""};
const body = {
  dataset: {},
  attributes: {},
  innerHTML: "",
  setAttribute(name, value) { this.attributes[name] = String(value); },
  querySelector(selector) {
    if (selector === "[data-v811-quote]") return quoteHost;
    if (selector === "[data-v811-forms]") return formsHost;
    return null;
  },
};
const drawer = {};
function button(tab) {
  return {
    dataset: {tab},
    attributes: {},
    classList: {
      active: false,
      toggle(name, enabled) { if (name === "active") this.active = Boolean(enabled); },
    },
    setAttribute(name, value) { this.attributes[name] = String(value); },
  };
}
const buttons = ["Overview", "Journey", "Emails", "Payments", "Files", "Activity"].map(button);
const location = {
  href: "https://booking.example/bookings/booking-1/overview?brand=wbm",
  pathname: "/bookings/booking-1/overview",
  search: "?brand=wbm",
};
function applyUrl(target) {
  const parsed = new URL(target, "https://booking.example");
  location.href = parsed.href;
  location.pathname = parsed.pathname;
  location.search = parsed.search;
}
const history = {
  state: {returnUrl: "/enquiries"},
  replaceState(next, _unused, target) { this.state = next; applyUrl(target); },
  pushState(next, _unused, target) { this.state = next; applyUrl(target); },
};
const record = {
  id: "booking-1", invoices: [], documents: [], tasks: [], activity: [],
};
const context = {
  console,
  URL,
  window: {},
  location,
  history,
  state: {brand: "wbm", current: record, currentPortal: {emails: [], submissions: []}},
  money: value => `£${Number(value).toFixed(2)}`,
  esc: value => String(value),
  toast: () => {},
  setTimeout: callback => callback(),
  normaliseRecordTab: tab => tab,
  recordSectionNavigation: () => "",
  renderTab: async (_record, tab) => calls.push(`composite:${tab}`),
  renderQuotePortal: async () => calls.push("quote"),
  renderOverview: () => calls.push("overview"),
  renderBookingEmails: () => calls.push("emails"),
  renderFinance: () => calls.push("payments"),
  renderRecordDocuments: () => calls.push("files"),
  $: selector => selector === "#drawer" ? drawer : selector === "#drawer-body" ? body : null,
  $$: selector => selector === "[data-tab]" ? buttons : [],
};
context.window = context;
context.WBMWorkspaceV895 = {
  renderFormsAndAgreement: () => calls.push("forms"),
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context, {filename: process.argv[1]});

(async () => {
  assert.strictEqual(context.WBMWorkspaceV844.version, "8.44");
  assert.deepStrictEqual(Array.from(context.WBMWorkspaceV844.sections),
    ["Overview", "Journey", "Emails", "Payments", "Files", "Activity"]);
  assert.strictEqual(context.WBMWorkspaceV844.canonicalSection("Forms"), "Journey");
  assert.strictEqual(context.WBMWorkspaceV844.canonicalSection("Notes"), "Activity");

  const navigation = context.recordSectionNavigation("Emails");
  assert(navigation.includes('data-tab="Emails"'));
  assert(navigation.includes('data-tab="Activity"'));
  assert(!navigation.includes("data-section-body"));

  await context.selectRecordTab(record, "Emails");
  assert.deepStrictEqual(calls.splice(0), ["emails"]);
  assert.strictEqual(body.dataset.v844Section, "Emails");
  assert.strictEqual(location.pathname, "/bookings/booking-1/emails");
  assert.strictEqual(buttons.find(item => item.dataset.tab === "Emails").classList.active, true);

  await context.selectRecordTab(record, "Forms");
  assert.deepStrictEqual(calls.splice(0), ["composite:Journey", "quote", "forms"]);
  assert.strictEqual(location.pathname, "/bookings/booking-1/journey");

  await context.selectRecordTab(record, "Payments");
  assert.deepStrictEqual(calls.splice(0), ["payments"]);

  await context.selectRecordTab(record, "Files");
  assert.deepStrictEqual(calls.splice(0), ["files"]);

  await context.selectRecordTab(record, "Notes");
  assert.deepStrictEqual(calls.splice(0), ["composite:Activity"]);
  assert.strictEqual(location.pathname, "/bookings/booking-1/activity");
})().catch(error => { console.error(error); process.exit(1); });
"""
    # Keep the browser-like runtime test independent of Python import state and
    # execute the same JavaScript file shipped to the client.
    result = subprocess.run(
        ["node", "-e", node_test, str(script_path)],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
