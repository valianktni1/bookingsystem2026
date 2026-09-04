/* V8.34 — protected accepted-invoice amendments before full payment. */
(() => {
  "use strict";

  const baseRenderFinanceV834 = renderFinance;
  const baseOpenRecordModalV834 = openRecordModal;

  function numeric(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function amendmentRow(item = {}) {
    return `<article class="v834-amendment-row">
      <div class="v834-amendment-fields">
        <label>Item to add<input data-v834-name maxlength="200" value="${attr(item.name || "")}" placeholder="For example: Complimentary extra hour" required></label>
        <label>Quantity<input data-v834-quantity type="number" min="1" max="24" step="1" value="${attr(item.quantity || 1)}" required></label>
        <label>Price each (£)<input data-v834-price type="number" min="0" max="100000" step="0.01" value="${attr(numeric(item.unit_price, 0).toFixed(2))}" required></label>
        <label class="v834-line-description">Extra wording (optional)<textarea data-v834-description maxlength="1000" rows="2" placeholder="This appears beneath the item on the invoice PDF">${esc(item.description || "")}</textarea></label>
      </div>
      <div class="v834-amendment-row-footer"><strong data-v834-line-total>${money(numeric(item.total, 0))}</strong><button type="button" class="mini danger-text" data-v834-remove>Remove</button></div>
    </article>`;
  }

  function amendmentItems(root) {
    return $$(".v834-amendment-row", root).map(row => ({
      name: row.querySelector("[data-v834-name]").value.trim(),
      description: row.querySelector("[data-v834-description]").value.trim() || null,
      quantity: numeric(row.querySelector("[data-v834-quantity]").value, 1),
      unit_price: numeric(row.querySelector("[data-v834-price]").value, 0),
    }));
  }

  function openInvoiceAmendment(record, invoice) {
    const originalItems = (invoice.line_items || []).filter(item => !item.manual_amendment);
    const existingItems = (invoice.line_items || []).filter(item => item.manual_amendment);
    const originalTotal = originalItems.reduce((sum, item) => sum + numeric(item.total), 0);
    const protectedLines = originalItems.map(item => `<div><span><strong>${esc(item.name || "Accepted package item")}</strong>${item.description ? `<small>${esc(item.description)}</small>` : ""}</span><b>${money(item.total)}</b></div>`).join("");

    showModal(
      `Amend invoice ${invoice.number}`,
      `<div class="full v834-safety"><i>✓</i><span><strong>The invoice number stays ${esc(invoice.number)}</strong><small>The couple's portal and PDF update immediately. No email is sent.</small></span></div>
       <section class="full v834-protected-lines"><header><div><small>ORIGINAL ACCEPTED QUOTE</small><strong>Protected package lines</strong></div><span>These cannot be removed here</span></header>${protectedLines}</section>
       <section class="full v834-additions"><header><div><small>LATER AGREED ITEMS</small><strong>Add invoice wording or an extra</strong></div><div><button type="button" class="secondary" id="v834-free-hour">＋ Complimentary extra hour</button><button type="button" class="secondary" id="v834-add-line">＋ Add item</button></div></header><div id="v834-amendment-rows">${existingItems.map(amendmentRow).join("")}</div></section>
       <section class="full v834-totals"><div><span>Original accepted items</span><strong>${money(originalTotal)}</strong></div><div><span>Revised invoice total</span><strong id="v834-revised-total">${money(invoice.total)}</strong></div><div><span>Already paid</span><strong>${money(invoice.paid)}</strong></div><div class="balance"><span>New outstanding balance</span><strong id="v834-revised-balance">${money(invoice.balance)}</strong></div></section>
       <label class="full">Reason for this change<textarea id="v834-reason" rows="3" minlength="3" maxlength="500" required placeholder="For example: Couple asked for the complimentary extra hour to be shown"></textarea><small class="field-help">Saved permanently in the private audit history.</small></label>`,
      async () => {
        const items = amendmentItems($("#v834-amendment-rows"));
        if (items.some(item => !item.name)) throw new Error("Give every added invoice item a name");
        if (items.some(item => !Number.isInteger(item.quantity) || item.quantity < 1 || item.quantity > 24)) throw new Error("Quantity must be a whole number from 1 to 24");
        const result = await api(`/api/invoices/${invoice.id}/amendment`, {
          method: "PUT",
          body: JSON.stringify({
            additional_items: items,
            reason: value("#v834-reason").trim(),
            expected_total: Number(invoice.total),
            expected_paid: Number(invoice.paid),
          }),
        });
        closeModal();
        await refresh();
        toast(`Invoice ${result.number} amended safely`);
        await openDrawer(record.id, "Payments");
      },
      "Available only while this accepted invoice still has money outstanding. It locks when paid in full."
    );

    const save = $("#dynamic-form footer .primary");
    if (save) save.textContent = "Save amended invoice";
    const rows = $("#v834-amendment-rows");

    function recalculate() {
      const extra = amendmentItems(rows).reduce((sum, item) => sum + item.quantity * item.unit_price, 0);
      const total = originalTotal + extra;
      $("#v834-revised-total").textContent = money(total);
      $("#v834-revised-balance").textContent = money(Math.max(0, total - numeric(invoice.paid)));
      $$(".v834-amendment-row", rows).forEach(row => {
        const quantity = numeric(row.querySelector("[data-v834-quantity]").value, 1);
        const price = numeric(row.querySelector("[data-v834-price]").value, 0);
        row.querySelector("[data-v834-line-total]").textContent = money(quantity * price);
      });
    }

    function wireRows() {
      $$('[data-v834-remove]', rows).forEach(button => button.onclick = () => {
        button.closest(".v834-amendment-row").remove();
        recalculate();
      });
      $$('[data-v834-quantity], [data-v834-price]', rows).forEach(input => input.oninput = recalculate);
      recalculate();
    }

    function addItem(item = {}) {
      rows.insertAdjacentHTML("beforeend", amendmentRow(item));
      wireRows();
      rows.lastElementChild?.querySelector("[data-v834-name]")?.focus();
    }

    $("#v834-add-line").onclick = () => addItem();
    $("#v834-free-hour").onclick = () => addItem({
      name: "Complimentary extra hour",
      description: "One additional hour of wedding photography coverage at no extra charge.",
      quantity: 1,
      unit_price: 0,
      total: 0,
    });
    wireRows();
  }

  renderFinance = function (record, body) {
    baseRenderFinanceV834(record, body);
    $$("[data-v82-invoice]", body).forEach(card => {
      const invoice = (record.invoices || []).find(item => item.id === card.dataset.v82Invoice);
      const actions = card.querySelector(".v82-invoice-actions");
      if (!invoice?.accepted_quote_invoice || !actions) return;
      actions.querySelector("[data-v82-delete-invoice]")?.remove();
      const amendments = (invoice.line_items || []).filter(item => item.manual_amendment);
      if (amendments.length && !card.querySelector(".v834-amended-summary")) {
        const payments = card.querySelector(".payments");
        payments?.insertAdjacentHTML("beforebegin", `<section class="v834-amended-summary"><small>LATER AGREED ITEMS</small>${amendments.map(item => `<div><span><strong>${esc(item.name)}</strong>${item.description ? `<em>${esc(item.description)}</em>` : ""}</span><b>${money(item.total)}</b></div>`).join("")}</section>`);
      }
      if (invoice.amendment_allowed) {
        actions.insertAdjacentHTML("afterbegin", `<button class="mini v834-amend-invoice" type="button">✎ Amend invoice</button>`);
        actions.querySelector(".v834-amend-invoice").onclick = () => openInvoiceAmendment(record, invoice);
      } else if (invoice.amendment_lock_reason === "Paid in full") {
        actions.insertAdjacentHTML("afterbegin", `<span class="v834-paid-lock">🔒 Paid in full · editing locked</span>`);
      }
    });
  };

  openRecordModal = function (record = null) {
    baseOpenRecordModalV834(record);
    if (!record || !(record.invoices || []).some(invoice => invoice.accepted_quote_invoice)) return;
    ["#form-package", "#form-total", "#form-deposit"].forEach(selector => {
      const input = $(selector);
      if (!input) return;
      input.readOnly = true;
      input.closest("label")?.insertAdjacentHTML("beforeend", `<small class="field-help">Protected by the accepted invoice. Use Amend invoice in Payments.</small>`);
    });
  };
})();
