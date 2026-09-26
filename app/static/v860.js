/* Remember navigation positions only. No form contents or booking data are stored. */
(() => {
  'use strict';
  let restoring = false, loggingOut = false, timer, stopRestore = () => {};
  const route = () => location.pathname + location.search;
  const authenticated = () => !document.querySelector('#app')?.classList.contains('hidden');
  const key = () => 'wbm-place-v860:' + (document.querySelector('#login-email')?.value || '').toLowerCase();
  const read = () => { try { return JSON.parse(sessionStorage.getItem(key()) || '{}'); } catch (_) { return {}; } };
  function save() {
    if (restoring || loggingOut || !authenticated()) return;
    const drawer = document.querySelector('#drawer');
    const snapshot = {route:route(), y:window.scrollY, drawer:drawer?.scrollTop || 0,
      body:document.querySelector('#drawer-body')?.scrollTop || 0,
      table:document.querySelector('#content .table-wrap')?.scrollLeft || 0};
    try {
      history.replaceState({...history.state, scrollY:snapshot.y, wbmPlace:snapshot}, '', location.href);
      const stored = read();
      stored[snapshot.route] = snapshot;
      // Bounded per-tab navigation memory, never client form/email contents.
      const entries = Object.entries(stored).filter(([name]) => name !== 'last').slice(-30);
      sessionStorage.setItem(key(), JSON.stringify({...Object.fromEntries(entries), last:snapshot.route}));
    } catch (_) { /* Private browsing/storage restrictions must not break navigation. */ }
  }
  function begin() {
    stopRestore();
    clearTimeout(timer);
    restoring = true;
    loggingOut = false;
    const stored = read();
    if (location.pathname === '/' && typeof stored.last === 'string' &&
        /^\/(?:bookings\/|dashboard(?:\?|$)|enquiries(?:\?|$)|weddings(?:\?|$)|calendar(?:\?|$)|communications(?:\?|$)|settings(?:\?|$)|invoices(?:\?|$)|packages(?:\?|$)|documents(?:\?|$)|workflows(?:\?|$)|projects(?:\?|$))/.test(stored.last)) {
      history.replaceState(history.state, '', stored.last);
    }
    const saved = history.state?.wbmPlace;
    return saved?.route === route() ? saved : stored[route()];
  }
  function finish(saved) {
    if (!saved || saved.route !== route() || !authenticated()) { restoring = false; return; }
    const target = route();
    let observer, timeout, frame;
    function apply() {
      if (route() !== target || !authenticated()) { stopRestore(); return; }
      const position = n => Math.max(0, Number(n) || 0);
      window.scrollTo({top:position(saved.y), behavior:'instant'});
      for (const [selector, field] of [['#drawer','drawer'],['#drawer-body','body']]) {
        const el = document.querySelector(selector);
        if (el) el.scrollTo({top:position(saved[field]), behavior:'instant'});
      }
      const table = document.querySelector('#content .table-wrap');
      if (table) table.scrollLeft = position(saved.table);
    }
    const events = ['pointerdown','touchstart','wheel','keydown'];
    stopRestore = () => {
      clearTimeout(timeout); cancelAnimationFrame(frame); observer?.disconnect();
      events.forEach(event => document.removeEventListener(event, stopRestore, true));
      restoring = false;
    };
    events.forEach(event => document.addEventListener(event, stopRestore, {capture:true, passive:true}));
    observer = new MutationObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(apply); });
    observer.observe(document.querySelector('#app'), {childList:true, subtree:true});
    // Booking sections may finish fetching after the outer route has returned.
    const drawer = document.querySelector('#drawer');
    if (drawer) observer.observe(drawer, {childList:true, subtree:true});
    frame = requestAnimationFrame(apply);
    timeout = setTimeout(() => { stopRestore(); save(); }, 2000);
  }
  document.addEventListener('scroll', () => {
    if (restoring) return;
    clearTimeout(timer); timer = setTimeout(save, 100);
  }, {capture:true, passive:true});
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') save(); });
  window.addEventListener('pagehide', save);
  document.querySelector('#logout')?.addEventListener('click', () => {
    loggingOut = true;
    stopRestore(); clearTimeout(timer);
    try { sessionStorage.removeItem(key()); history.replaceState({...history.state, wbmPlace:null, scrollY:0}, '', location.href); } catch (_) {}
  }, true);
  window.WBMPlace = {save, begin, finish};
})();
