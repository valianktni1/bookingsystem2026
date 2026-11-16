(() => {
  "use strict";
  const s=window.WBMStorybooks, esc=s.esc;
  const endpoint="/api/storybooks/form";
  const id=()=>crypto.randomUUID().replaceAll("-","");
  const checkbox=(name,label,on)=>`<label class="sb-editor-check"><input name="${name}" type="checkbox" ${on?"checked":""}> ${label}</label>`;

  function dialog(title,content) {
    const el=document.createElement("dialog");
    el.className="sb-dialog sb-form-editor";
    el.setAttribute("aria-label",title);
    el.innerHTML=`<h2>${esc(title)}</h2>${content}`;
    document.body.append(el);
    el.addEventListener("close",()=>el.remove(),{once:true});
    return el;
  }

  function preview(config) {
    const el=dialog("Preview enquiry form",'<p>Preview only. Nothing you enter here will be sent.</p><button class="sb-secondary" type="button" data-back>Back to editing</button><section data-preview></section><h3>After someone submits</h3><p data-thanks></p>');
    el.querySelector("[data-preview]").innerHTML=s.publicContent(config);
    el.querySelector("[data-thanks]").textContent=config.thanks;
    const form=el.querySelector("form");
    form.addEventListener("submit",event=>event.preventDefault());
    form.querySelector('[type="submit"]').disabled=true;
    s.wire(form,config.questions);
    el.querySelector("[data-back]").onclick=()=>el.close();
    el.showModal();
  }

  async function open() {
    const {config}=await api(endpoint);
    const el=dialog("Edit storybook enquiry form",`
      <p>These settings are for the public storybook form. Your wedding enquiry form and existing orders stay as they are.</p>
      <form>
        <fieldset><legend>Wording</legend><div class="sb-grid">
          ${s.input("title","Heading",config.title,'required maxlength="120"')}
          ${s.input("button","Send button text",config.button,'required maxlength="120"')}
          <label class="sb-wide">Introduction<textarea name="intro" rows="4" required maxlength="1000">${esc(config.intro)}</textarea></label>
          <label class="sb-wide">Thank you message<textarea name="thanks" rows="3" required maxlength="1000">${esc(config.thanks)}</textarea></label>
        </div></fieldset>
        <fieldset><legend>Story choices</legend>
          <p>Untick a story to take it off the form. New stories use the standard personalisation questions and are priced when you create the invoice.</p>
          <div data-stories></div><button type="button" class="sb-secondary" data-add-story>Add a story</button>
        </fieldset>
        <fieldset><legend>Extra questions</legend>
          <p>Ask something about every order, or just one story. The standard contact, book and consent fields stay in place.</p>
          <div data-questions></div><button type="button" class="sb-secondary" data-add-question>Add a question</button>
        </fieldset>
        <p class="sb-error" role="alert"></p>
        <div class="sb-actions">
          <button type="submit" class="sb-primary">Publish changes</button>
          <button type="button" class="sb-secondary" data-preview>Preview</button>
          <button type="button" class="sb-secondary" data-close>Cancel</button>
        </div>
      </form>`);
    const form=el.querySelector("form"), stories=el.querySelector("[data-stories]"), questions=el.querySelector("[data-questions]");
    const error=form.querySelector("[role=alert]");
    const controls=[...form.querySelectorAll(".sb-actions button")];

    function addStory(story) {
      stories.insertAdjacentHTML("beforeend",`<div class="sb-editor-row" data-story="${esc(story.id)}">
        ${s.input("label","Story name",story.label,'required maxlength="120"')}
        ${checkbox("enabled","Show on the form",story.enabled)}
        ${story.id.startsWith("story_")?'<button type="button" class="sb-secondary" data-remove-story>Remove story</button>':""}
        </div>`);
    }
    function syncStories() {
      const choices=[...stories.children].map(row=>[row.dataset.story,s.val(row,"label")||"New story"]);
      for(const select of questions.querySelectorAll('[name="story"]')){
        const selected=select.value || select.dataset.initial;
        select.innerHTML='<option value="">All stories</option>'+choices.map(([key,name])=>`<option value="${esc(key)}">${esc(name)}</option>`).join("");
        select.value=choices.some(([key])=>key===selected)?selected:"";
        delete select.dataset.initial;
      }
      form.querySelector("[data-add-story]").disabled=stories.children.length>=50;
      form.querySelector("[data-add-question]").disabled=questions.children.length>=20;
    }
    function addQuestion(q) {
      questions.insertAdjacentHTML("beforeend",`<div class="sb-editor-row sb-grid" data-question="${esc(q.id)}">
        <div class="sb-wide">${s.input("label","Question",q.label,'required maxlength="120"')}</div>
        <label>Answer type<select name="kind"><option value="text">Short text</option><option value="paragraph">Long text</option><option value="date">Date</option></select></label>
        <label>Show for<select name="story" data-initial="${esc(q.story)}"></select></label>
        ${checkbox("required","Answer required",q.required)}
        <button type="button" class="sb-secondary" data-remove-question>Remove question</button>
      </div>`);
      questions.lastElementChild.querySelector('[name="kind"]').value=q.kind;
    }
    config.stories.forEach(addStory);
    config.questions.forEach(addQuestion);
    syncStories();

    function read() {
      const data={
        title:s.val(form,"title"),intro:s.val(form,"intro"),button:s.val(form,"button"),thanks:s.val(form,"thanks"),
        stories:[...stories.children].map(row=>({id:row.dataset.story,label:s.val(row,"label"),enabled:row.querySelector('[name="enabled"]').checked})),
        questions:[...questions.children].map(row=>({id:row.dataset.question,label:s.val(row,"label"),kind:s.val(row,"kind"),story:s.val(row,"story"),required:row.querySelector('[name="required"]').checked}))
      };
      if([data.title,data.intro,data.button,data.thanks,...data.stories.map(item=>item.label),...data.questions.map(item=>item.label)].some(x=>!x))
        throw new Error("Please fill in each heading, story name and question before continuing.");
      const visible=data.stories.filter(x=>x.enabled).map(x=>x.label.toLowerCase());
      if(!visible.length || visible.length!==new Set(visible).size)
        throw new Error("Keep at least one visible story and give each visible story a different name.");
      return data;
    }

    form.querySelector("[data-add-story]").onclick=()=>{
      addStory({id:"story_"+id(),label:"",enabled:true});syncStories();stories.lastElementChild.querySelector("input").focus();
    };
    form.querySelector("[data-add-question]").onclick=()=>{
      addQuestion({id:id(),label:"",kind:"text",story:null,required:false});syncStories();questions.lastElementChild.querySelector("input").focus();
    };
    stories.oninput=event=>{if(event.target.name==="label")syncStories();};
    stories.onclick=event=>{
      if(!event.target.closest("[data-remove-story]"))return;
      const row=event.target.closest("[data-story]");
      if([...questions.querySelectorAll('[name="story"]')].some(select=>select.value===row.dataset.story)){
        error.textContent="Remove or reassign this story’s extra questions first, or hide the story to keep them.";
        row.querySelector("input").focus();
        return;
      }
      row.remove();syncStories();form.querySelector("[data-add-story]").focus();
    };
    questions.onclick=event=>{
      if(!event.target.closest("[data-remove-question]"))return;
      event.target.closest("[data-question]").remove();syncStories();form.querySelector("[data-add-question]").focus();
    };
    form.querySelector("[data-close]").onclick=()=>el.close();
    form.querySelector("[data-preview]").onclick=()=>{
      error.textContent="";
      if(form.reportValidity()){
        try{preview(read());}catch(e){error.textContent=e.message;}
      }
    };
    let saving=false;
    el.addEventListener("cancel",event=>{if(saving)event.preventDefault();});
    form.onsubmit=async event=>{
      event.preventDefault();
      if(saving)return;
      error.textContent="";
      let body;
      try{body=JSON.stringify(read());}catch(e){error.textContent=e.message;return;}
      saving=true;
      controls.forEach(button=>button.disabled=true);
      try{
        await api(endpoint,{method:"PUT",body});
        el.close();toast("Storybook enquiry form published");
      }catch(e){error.textContent=e.message;}
      finally{saving=false;controls.forEach(button=>button.disabled=false);}
    };
    el.showModal();
  }

  window.WBMStorybookEditor={open};
})();
