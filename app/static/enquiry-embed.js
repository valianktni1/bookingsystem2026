(function () {
  const script = document.currentScript;
  const iframeId = script?.dataset.iframeId || "wbm-enquiry-form";
  const frame = document.getElementById(iframeId);
  if (!frame) return;
  const allowedOrigin = new URL(frame.src, location.href).origin;
  window.addEventListener("message", event => {
    if (event.origin !== allowedOrigin || event.source !== frame.contentWindow) return;
    if (!["wbm-enquiry-height", "wbm-enquiry-submitted"].includes(event.data?.type)) return;
    const height = Math.max(500, Math.min(5000, Number(event.data.height) || 0));
    frame.style.height = `${height}px`;
    if (event.data.type === "wbm-enquiry-submitted") {
      frame.dataset.enquirySubmitted = "true";
      requestAnimationFrame(() => frame.scrollIntoView({behavior: "smooth", block: "center"}));
    }
  });
})();
