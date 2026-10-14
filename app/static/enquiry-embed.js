(function () {
  const script = document.currentScript;
  const iframeId = script?.dataset.iframeId || "wbm-enquiry-form";
  const frame = document.getElementById(iframeId);
  if (!frame || frame.dataset.wbmResizeBound) return;
  // WordPress lazy loading can temporarily remove iframe.src. The script is
  // served by the booking app, so its origin remains trustworthy and stable.
  const allowedOrigin = new URL(script.src, location.href).origin;
  frame.dataset.wbmResizeBound = "true";
  Object.assign(frame.style, {display:"block",width:"100%",maxWidth:"100%",minWidth:"0",border:"0"});
  if (frame.closest(".wbm-contact .wbm-enquiry")) {
    const style = document.createElement("style");
    style.textContent = `
      .wbm-contact .wbm-enquiry .wbm-inner,
      .wbm-contact .wbm-form-wrap,
      .wbm-contact .wbm-form-wrap .elementor-widget-html,
      .wbm-contact .wbm-form-wrap .elementor-widget-container {width:100%;min-width:0;max-width:100%}
      .wbm-contact .wbm-form-wrap {padding-inline:0}
      @media(max-width:767px){
        .wbm-contact .wbm-enquiry {padding-inline:12px}
        .wbm-contact .wbm-enquiry .wbm-inner,
        .wbm-contact .wbm-form-wrap .elementor-widget-container {padding-inline:0}
      }`;
    document.head.append(style);
  }
  const requestHeight = () => frame.contentWindow?.postMessage({type:"wbm-enquiry-resize"}, allowedOrigin);
  frame.addEventListener("load", requestHeight);
  window.addEventListener("message", event => {
    if (event.origin !== allowedOrigin || event.source !== frame.contentWindow) return;
    if (!["wbm-enquiry-height", "wbm-enquiry-started", "wbm-enquiry-submitted"].includes(event.data?.type)) return;
    if (event.data.type === "wbm-enquiry-started") {
      window.wbmWebsiteEvent?.("enquiry_start");
      return;
    }
    const value = Number(event.data.height);
    if (!Number.isFinite(value) || value <= 0) return;
    const height = Math.max(360, Math.min(30000, Math.ceil(value)));
    frame.style.minHeight = "0";
    if (frame.style.height !== `${height}px`) frame.style.height = `${height}px`;
    if (event.data.type === "wbm-enquiry-submitted") {
      frame.dataset.enquirySubmitted = "true";
      window.wbmWebsiteEvent?.("enquiry_success");
      requestAnimationFrame(() => frame.scrollIntoView({behavior: "smooth", block: "center"}));
    }
  });
  requestHeight();
})();
