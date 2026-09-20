/* V8.53 — personal studio polish. Keeps mobile navigation state and Inbox count clear. */
(() => {
  const desktopCount = document.querySelector("#mail-nav-count");
  const mobileCount = document.querySelector("#mobile-mail-count");

  function mirrorUnreadCount() {
    if (!desktopCount || !mobileCount) return;
    mobileCount.textContent = desktopCount.textContent || "0";
    mobileCount.classList.toggle("hidden", desktopCount.classList.contains("hidden") || Number(desktopCount.textContent || 0) < 1);
  }

  function syncMobileLocation() {
    const active = document.querySelector(".mobile-nav button.active[data-view]");
    document.querySelectorAll(".mobile-nav button[data-view]").forEach(button => {
      if (button === active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
  }

  if (desktopCount) new MutationObserver(mirrorUnreadCount).observe(desktopCount, {attributes:true,childList:true,characterData:true,subtree:true});
  const mobileNav = document.querySelector(".mobile-nav");
  if (mobileNav) new MutationObserver(syncMobileLocation).observe(mobileNav, {attributes:true,subtree:true,attributeFilter:["class"]});
  document.addEventListener("click", event => {
    if (event.target.closest(".mobile-nav button")) requestAnimationFrame(syncMobileLocation);
  });
  mirrorUnreadCount();
  syncMobileLocation();
})();
