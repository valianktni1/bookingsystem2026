/* V8.56: display-only payment summary; no payment state is written. */
(() => {
  'use strict';
  function nextPayment(record, today = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())) {
    if (record?.legacy_source || record?.brand !== 'wbm') return '';
    const invoices = (record.invoices || []).filter(item => !item.legacy_source && !['void','cancelled'].includes(item.status) && Number(item.balance) > 0);
    if (!invoices.length) return '';
    const rows = invoices.flatMap(item => {
      if (item.payment_schedule?.length) return item.payment_schedule.filter(row => Number(row.balance) > 0).map(row => ({date:row.due_date, amount:Number(row.balance)}));
      return [{date:item.payment_due_date || item.due_date, amount:Number(item.balance)}];
    });
    const dated = rows.filter(row => /^\d{4}-\d{2}-\d{2}$/.test(row.date || '')).sort((a,b) => a.date.localeCompare(b.date));
    if (!dated.length) return 'Payment date not set';
    const date = dated[0].date;
    const amount = dated.filter(row => row.date === date).reduce((sum,row) => sum + row.amount, 0);
    const label = date < today ? 'Overdue since' : date === today ? 'Due today' : 'Due';
    const missing = rows.length !== dated.length ? ' · Other payment dates need checking' : '';
    return `${money(amount)} · ${label}${date === today ? '' : ` ${fmtDate(date)}`}${missing}`;
  }
  window.WBMUsabilityV856 = Object.freeze({nextPayment});
})();
