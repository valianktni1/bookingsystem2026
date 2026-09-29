/* Appearance is device-local. Runs before paint; no account or booking writes. */
(() => {
  const key = 'wbm-appearance', media = matchMedia('(prefers-color-scheme: dark)');
  let choice = 'system';
  try { choice = localStorage.getItem(key) || 'system'; } catch (_) {}
  if (!['system','light','dark'].includes(choice)) choice = 'system';
  function apply() {
    const actual = choice === 'system' ? (media.matches ? 'dark' : 'light') : choice;
    document.documentElement.dataset.wbmTheme = actual;
    document.documentElement.style.colorScheme = actual;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content',actual === 'dark' ? '#17211d' : '#f3f6f4');
    document.querySelectorAll('[data-wbm-appearance]').forEach(el => el.value = choice);
  }
  media.addEventListener('change',apply);
  window.addEventListener('storage',e=>{if(e.key===key){choice=['light','dark'].includes(e.newValue)?e.newValue:'system';apply();}});
  document.addEventListener('change',e=>{
    if(!e.target.matches('[data-wbm-appearance]'))return;
    choice=e.target.value;
    try { localStorage.setItem(key,choice); } catch (_) {}
    apply();
  });
  window.WBMAppearance={apply,get:()=>choice};apply();
})();
