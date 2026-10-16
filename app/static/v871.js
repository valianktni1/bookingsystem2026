/* Personal WBM planner invitation connection. Off until deliberately enabled. */
(() => {
 const original = renderSettings;
 renderSettings = async function(...args) {
   await original.apply(this,args);
   const host = document.querySelector('#content');
   if (!host || document.querySelector('#planner-invitations-open')) return;
   const section = document.createElement('section');section.className='panel';
   section.innerHTML='<h2>Complimentary wedding planner</h2><p>Invite new Weddings By Mark couples 30 minutes after their deposit confirmation email is sent.</p><button type="button" class="primary" id="planner-invitations-open">Planner invitations</button>';
   host.prepend(section);section.querySelector('button').onclick=openPlannerConnection;
 };
 async function openPlannerConnection() {
   try {
     const [settings,jobs]=await Promise.all([api('/api/planner-invitations/settings'),api('/api/planner-invitations/jobs')]);
     const labels={pending:'Scheduled',sending:'Connecting',retry:'Retry scheduled',queued:'Email queued in planner',sent:'Invitation sent',accepted:'Invitation accepted',needs_attention:'Needs attention',cancelled:'Not eligible'};
     showModal('Planner invitations',`<p class="full">Only new payment confirmations sent after you enable this connection are included. Existing bookings and protected Studio Ninja imports are excluded. The full booking deposit must be recorded as paid.</p><p class="full">In planner admin, open System &amp; security and create a booking connection key. Paste it below.</p><label class="full">Connection key<input id="planner-key" type="password" autocomplete="new-password" maxlength="200" placeholder="${settings.key_saved?'Saved — leave blank to keep it':'Paste the key from planner admin'}"></label><label class="full"><span><input id="planner-enabled" type="checkbox" ${settings.enabled?'checked':''} style="width:20px;height:20px"> Enable automatic complimentary invitations</span></label><p class="full">Delay: <strong>30 minutes</strong> after confirmation is sent. Access ends <strong>30 days after the wedding</strong>. Both first names, main email and wedding date are required.</p><section class="full"><h3>Recent invitations</h3>${jobs.map(job=>`<article style="padding:12px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere"><strong>${esc(job.couple)}</strong><p>${esc(labels[job.status]||job.status)} · Due ${esc(fmtDateTime(job.due_at))}</p>${job.error?`<p>${esc(job.error)}</p>`:''}${['needs_attention','retry','cancelled'].includes(job.status)?`<button type="button" class="secondary" data-planner-retry="${attr(job.booking_id)}">Retry / check status</button>`:''}</article>`).join('')||'<p>No invitations scheduled yet.</p>'}</section>`,async()=>{
       const button=document.querySelector('#dynamic-form button[type=submit]');button.disabled=true;
       try{await api('/api/planner-invitations/settings',{method:'PUT',body:JSON.stringify({enabled:document.querySelector('#planner-enabled').checked,key:document.querySelector('#planner-key').value||null})});closeModal();toast('Planner connection saved');}
       catch(error){button.disabled=false;throw error;}
     },'Set up the connection and check invitation progress. Saving does not invite older bookings.');
     document.querySelectorAll('[data-planner-retry]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await api('/api/planner-invitations/jobs/'+button.dataset.plannerRetry+'/retry',{method:'POST'});button.textContent='Retry scheduled';}catch(error){button.disabled=false;toast(error.message,'error');}});
   }catch(error){toast(error.message,'error');}
 }
})();
