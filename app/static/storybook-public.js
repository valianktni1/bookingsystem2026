(() => {
  const s=window.WBMStorybooks, order=document.querySelector("#order"), main=document.querySelector("main");
  const allowed=["https://perfectweddingsbymark.uk","https://www.perfectweddingsbymark.uk","https://ivorydigital.uk","https://www.ivorydigital.uk"];
  const sendHeight=(type="wbm-enquiry-height")=>{
    if(window.parent===window)return;
    const height=Math.ceil(main.getBoundingClientRect().height)+2;
    for(const origin of allowed) window.parent.postMessage({type,height},origin);
  };
  new ResizeObserver(()=>sendHeight()).observe(main);
  window.addEventListener("message",event=>{
    if(event.source===window.parent&&allowed.includes(event.origin)&&event.data?.type==="wbm-enquiry-resize")sendHeight();
  });
  async function load(){
    try{
      const response=await fetch("/api/public/storybooks/form",{cache:"no-store"});
      if(!response.ok)throw new Error();
      const {config,revision}=await response.json();
      order.innerHTML=s.publicContent(config);
      s.requestForm(order.querySelector("form"),"/api/public/storybooks",{publicOrder:true,config,revision,onSuccess:()=>{
        order.hidden=true;
        const thanks=document.querySelector("#storybook-thanks");
        thanks.innerHTML="<h1>Thank you</h1><p>"+s.esc(config.thanks)+"</p>";
        thanks.hidden=false;thanks.focus({preventScroll:true});
        if(window.parent===window)thanks.scrollIntoView({block:"start"});
        else requestAnimationFrame(()=>sendHeight("wbm-storybook-submitted"));
      }});
    }catch{
      order.innerHTML='<h1>Order a personalised storybook</h1><p role="alert">The form couldn’t load just now.</p><button type="button" class="sb-primary">Try again</button>';
      order.querySelector("button").onclick=event=>{event.currentTarget.disabled=true;load();};
    }
  }
  load();
})();
