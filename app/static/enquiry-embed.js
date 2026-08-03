(function () {
  const script = document.currentScript;
  const iframeId = script?.dataset.iframeId || "wbm-enquiry-form";
  const frame = document.getElementById(iframeId);
  if (!frame) return;
  const allowedOrigin = new URL(frame.src, location.href).origin;
  window.addEventListener("message", event => {
    if (event.origin !== allowedOrigin || event.source !== frame.contentWindow) return;
    if (event.data?.type !== "wbm-enquiry-height") return;
    const height = Math.max(500, Math.min(5000, Number(event.data.height) || 0));
    frame.style.height = `${height}px`;
  });
})();
