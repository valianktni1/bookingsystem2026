(() => {
  const s=window.WBMStorybooks, form=document.querySelector("#storybook-request"), main=document.querySelector("main");
  form.innerHTML=s.fields({}, {}) + s.consent + '<label class="sb-website" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label><p class="sb-error" role="alert" data-sb-error></p><button class="sb-primary" type="submit">Send storybook order request</button>';
  const allowed=["https://perfectweddingsbymark.uk","https://www.perfectweddingsbymark.uk"];
  const sendHeight=(type="wbm-enquiry-height")=>{
    if(window.parent===window)return;
    const height=Math.ceil(main.getBoundingClientRect().height)+2;
    for(const origin of allowed) window.parent.postMessage({type,height},origin);
  };
  new ResizeObserver(()=>sendHeight()).observe(main);
  window.addEventListener("message",event=>{
    if(event.source===window.parent&&allowed.includes(event.origin)&&event.data?.type==="wbm-enquiry-resize")sendHeight();
  });
  s.requestForm(form,"/api/public/storybooks",{publicOrder:true,onSuccess:()=>{
    document.querySelector("#order").hidden=true;
    const thanks=document.querySelector("#storybook-thanks");
    thanks.innerHTML="<h1>Thank you</h1><p>"+s.esc(s.success)+"</p>";
    thanks.hidden=false;thanks.focus({preventScroll:true});
    if(window.parent===window)thanks.scrollIntoView({block:"start"});
    else requestAnimationFrame(()=>sendHeight("wbm-storybook-submitted"));
  }});
})();
