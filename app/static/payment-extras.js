/* Read-only booked-extras summary. Invoice rows and totals remain untouched. */
(() => {
  'use strict';
  const baseRenderFinance = renderFinance;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const currency = value => new Intl.NumberFormat('en-GB', {style:'currency',currency:'GBP'}).format(value);
  const normal = value => String(value ?? '').trim().toLowerCase().replace(/\s+/g,' ');
  const extraKinds = new Set(['addon','add_on','extra','optional_extra','required_extra']);

  function number(value) {
    if (typeof value !== 'string' && typeof value !== 'number') return null;
    if (String(value).trim() === '') return null;
    const parsed = Number(String(value).replace(/[£,]/g,'').trim());
    return Number.isFinite(parsed) ? parsed : null;
  }

  function lineTotal(line, quantity) {
    for (const key of ['total','line_total','amount']) {
      const value = number(line[key]);
      if (value !== null) return value;
    }
    for (const key of ['unit_price','price','rate']) {
      const value = number(line[key]);
      if (value !== null) return value * quantity;
    }
    return null;
  }

  function namedExtra(name) {
    return /\b(?:photo[\s-]*booth|selfie[\s-]*booth|albums?|extra\s+(?:hours?|coverage|photographer|videographer)|additional\s+(?:hours?|coverage|photographer|videographer)|travel\s+(?:expenses?|costs?|charge))\b/i.test(name);
  }

  function extraItem(line, record, source) {
    if (!line || typeof line !== 'object' || Array.isArray(line)) return null;
    const name = String(line.name || line.title || line.description || '').trim();
    if (!name) return null;
    const kind = normal(line.type || line.kind).replace(/[\s-]+/g,'_');
    const quantity = number(line.quantity ?? line.qty ?? 1);
    if (quantity === null || quantity <= 0) return null;
    const total = lineTotal(line, quantity);
    if (kind === 'discount' || line.discount === true || line.is_discount === true
        || (total !== null && total < 0)) return null;
    if (kind === 'package' || line.is_package === true) return null;
    const explicitlyExtra = extraKinds.has(kind) || line.is_addon === true
      || Boolean(line.addon_id) || line.manual_amendment === true;
    if (!explicitlyExtra) {
      // Older exports may not tag item types. Only recognise separately named
      // extras, never scan a package's included-features description.
      if ((kind && !['item','line_item','service','product'].includes(kind))
          || normal(name) === normal(record.package_name) || /\b(?:package|discount)\b/i.test(name)
          || !namedExtra(name)) return null;
    }
    return {name, quantity, total, addedLater:line.manual_amendment === true,
      invoiceId:source.id, invoiceNumber:source.number || ''};
  }

  function items(record, quote) {
    const invoices = Array.isArray(record.invoices) ? record.invoices : [];
    const result = [];
    invoices.filter(invoice => !['void','cancelled'].includes(normal(invoice.status))).forEach(invoice => {
      let lines = Array.isArray(invoice.line_items) ? invoice.line_items : [];
      const hasSavedLines = lines.some(line => line && typeof line === 'object'
        && !Array.isArray(line) && String(line.name || line.title || line.description || '').trim());
      if (!hasSavedLines && quote?.status === 'accepted' && quote.invoice_id === invoice.id) {
        lines = Array.isArray(quote.line_items) ? quote.line_items : [];
      }
      const namedLines = lines.some(line => line && typeof line === 'object'
        && !Array.isArray(line) && String(line.name || line.title || line.description || '').trim());
      // A separate imported invoice such as "Album add-on" is itself evidence
      // of an extra. A package invoice mentioning included albums is not.
      if (!namedLines && typeof invoice.description === 'string'
          && invoice.description.length <= 160 && !/[\r\n]/.test(invoice.description)) {
        const candidate = extraItem({name:invoice.description,total:invoice.total},record,invoice);
        if (candidate) result.push(candidate);
      } else {
        lines.forEach(line => {const item = extraItem(line,record,invoice);if (item) result.push(item);});
      }
    });
    return result;
  }

  function render(record, quote) {
    const extras = items(record,quote);
    const multipleInvoices = new Set(extras.map(item => item.invoiceId)).size > 1;
    const list = extras.length ? `<ul>${extras.map(item => `<li>
      <div><strong>${item.quantity !== 1 ? escape(item.quantity) + ' × ' : ''}${escape(item.name)}</strong>
      ${item.addedLater || (multipleInvoices && item.invoiceNumber) ? `<small>${[item.addedLater ? 'Added later' : '',multipleInvoices && item.invoiceNumber ? 'Invoice ' + escape(item.invoiceNumber) : ''].filter(Boolean).join(' · ')}</small>` : ''}</div>
      <span class="payment-extras-price">${item.total === null ? 'Price not recorded' : item.total === 0 ? 'No extra charge' : currency(item.total)}</span>
    </li>`).join('')}</ul>` : `<p class="payment-extras-empty">No separately listed extras found.${record.legacy_source ? ' Older imported invoices may not have itemised extras.' : ''}</p>`;
    return `<section class="payment-extras-summary" aria-label="Add-ons and extras"><header><h3>Add-ons / extras</h3>${extras.length ? `<span>${extras.length} booked extra${extras.length === 1 ? '' : 's'}</span>` : ''}</header>${list}</section>`;
  }

  renderFinance = function(record,body) {
    baseRenderFinance.apply(this,arguments);
    body.querySelector('.payment-extras-summary')?.remove();
    const heading = body.querySelector('.section-actions');
    if (heading) heading.insertAdjacentHTML('afterend',render(record,state.currentPortal?.quote));
  };
  window.WBMPaymentExtras = Object.freeze({items,render});
})();
