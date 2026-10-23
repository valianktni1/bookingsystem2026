/* A display filter for the email list. Uses the server's current usage labels. */
(() => {
  'use strict';
  const choices = [['all', 'All emails'], ['automatic', 'Automatic'],
    ['manual', 'Manual'], ['action', 'Workflow actions'], ['inactive', 'Inactive']];
  const selection = {kind: 'all', search: ''};
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));

  function kind(template) {
    if (template.is_active === false || template.usage_kind === 'inactive') return 'inactive';
    return ['automatic','action','manual'].includes(template.usage_kind) ? template.usage_kind : 'manual';
  }

  function render(templates) {
    return `<div class="email-template-filters">
      <div class="email-template-filter-heading">Show email templates</div>
      <div class="email-template-filter-buttons" role="group" aria-label="Filter email templates by how they are used">
        ${choices.map(([value,label]) => {
          const count = value === 'all' ? templates.length : templates.filter(t => kind(t) === value).length;
          return `<button type="button" data-email-template-filter="${value}" aria-pressed="${selection.kind === value}" aria-controls="email-template-list">${label}<span aria-hidden="true">${count}</span></button>`;
        }).join('')}
      </div>
      <label class="email-template-search-label" for="email-template-search">Find a template</label>
      <div class="email-template-search-row">
        <input id="email-template-search" type="search" placeholder="Search by name or subject" value="${escape(selection.search)}" aria-controls="email-template-list" autocomplete="off">
        <button type="button" data-email-template-clear>Clear filters</button>
      </div>
      <p id="email-template-filter-count" role="status" aria-live="polite" aria-atomic="true"></p>
    </div>`;
  }

  function wire(panel) {
    if (!panel) return;
    const input = panel.querySelector('#email-template-search');
    if (!input) return;
    const rows = Array.from(panel.querySelectorAll('[data-email-template-kind]'));
    const buttons = Array.from(panel.querySelectorAll('[data-email-template-filter]'));
    const empty = document.createElement('div');
    empty.className = 'email-template-filter-empty';
    empty.hidden = true;
    empty.innerHTML = '<strong>No matching email templates</strong><p>Choose another category or clear your search.</p>';
    panel.querySelector('#email-template-list').append(empty);

    function apply() {
      const query = selection.search.trim().toLocaleLowerCase();
      let shown = 0;
      rows.forEach(row => {
        const match = (selection.kind === 'all' || row.dataset.emailTemplateKind === selection.kind)
          && (!query || row.dataset.emailTemplateSearch.includes(query));
        row.hidden = !match;
        if (match) shown++;
      });
      buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.emailTemplateFilter === selection.kind)));
      panel.querySelector('#email-template-filter-count').textContent = `Showing ${shown} of ${rows.length} email templates`;
      empty.hidden = shown > 0 || rows.length === 0;
    }

    buttons.forEach(button => button.addEventListener('click', () => {
      selection.kind = button.dataset.emailTemplateFilter;
      apply();
    }));
    input.addEventListener('input', () => { selection.search = input.value; apply(); });
    panel.querySelector('[data-email-template-clear]').addEventListener('click', () => {
      selection.kind = 'all'; selection.search = ''; input.value = ''; apply();
    });
    apply();
  }

  window.WBMEmailTemplateFilters = Object.freeze({render,kind,wire});
})();
