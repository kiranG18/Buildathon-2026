/* Every action sends a request to the API, then re-reads state. The browser holds no engine. */

async function run(fn,opts){
 opts=opts||{};
 try{
  if(opts.optimistic){opts.optimistic();repaint()}
  const r=await fn();
  if(opts.optimistic)hydrate(true).then(repaint).catch(()=>{});else await hydrate(true);
  if(opts.ok)toast(typeof opts.ok==='function'?opts.ok(r):opts.ok,opts.toast);
  if(opts.after)opts.after(r);
  repaint();
  return r;
 }catch(e){
  toast(e.message,{bad:true});
  if(opts.optimistic)await hydrate(true).catch(()=>{});
  repaint();
  return null;
 }
}
const idOf=t=>t.dataset.id;

/* ---------- session ---------- */
async function signIn(email,password){
 try{
  const r=await call('POST','/auth/login',{email,password},{keepSession:true});
  setToken(r.token);
  UI.path='/overview';try{location.hash='#/overview'}catch(e){}
  await hydrate(true);paint();
 }catch(e){
  const el=$('#lerr');if(el){el.hidden=false;el.textContent=e.status===429?e.message:'Email or password is wrong.'}
 }
}
ACT.login=()=>signIn($('#lem').value.trim(),$('#lpw').value);
ACT.logout=()=>{signOut();paint()};
ACT.killAsk=()=>confirmBox('Stop all outreach','Every campaign halts at once. In-flight jobs finish and nothing new sends until you resume the platform.','Stop everything',()=>run(()=>api.post('/kill-switch',{active:true}),{ok:'Kill switch on. All outreach is halted.',toast:{bad:true}}),true);
ACT.killOff=()=>run(()=>api.post('/kill-switch',{active:false}),{ok:'Platform resumed. Held jobs continue.'});

/* ---------- traces ---------- */
ACT.retry=t=>run(()=>api.post('/agent-runs/'+idOf(t)+'/retry'),{ok:'Job queued again. The worker picks it up in a moment.',after:()=>closeDrawer()});
ACT.replay=async t=>{
 const v=+$('#rpv').value,j=S.jobs.find(x=>x.id===idOf(t));
 try{
  const r=await api.post('/agent-runs/'+j.id+'/replay',{version:v});
  await hydrate(true);
  const d=r.diff,fmt=cls=>d.filter(x=>x.type==='same'||x.type===cls).map(x=>x.type===cls?`<span class="${cls}">${esc(x.text)}</span>`:esc(x.text)).join(' ');
  $('#rpout').innerHTML=`<div class="grid g2"><div><div class="lbl small">${r.label}, v${r.original_version} (original)</div><div class="pre diff" style="margin-top:6px">${fmt('del')}</div></div><div><div class="lbl small">${r.label}, v${v} (replay) <span class="tag replay">REPLAY</span></div><div class="pre diff" style="margin-top:6px">${fmt('add')}</div></div></div>`;
 }catch(e){toast(e.message,{bad:true})}
};

/* ---------- approvals, escalations, conflicts ---------- */
ACT.approve=t=>{const et=$('#editText');const edit=et&&!$('#draftEdit').hidden?et.value:null;
 run(()=>api.post('/approvals/'+idOf(t)+'/decide',{decision:'approve',edited_body:edit}),{ok:r=>r.msg||'Done',toast:{},after:()=>{UI.sel.appr=null}}).then(r=>{if(r&&!r.ok)toast(r.msg,{bad:true})});
};
ACT.approvePd=t=>run(()=>api.post('/approvals/'+idOf(t)+'/decide',{decision:'approve'}),{ok:r=>r.msg||'Done'});
ACT.rejectAsk=t=>{const id=idOf(t);openModal(`<h2>Reject with a reason</h2><p class="muted" style="margin-top:6px">The reason is saved on the prospect and helps the next prompt version.</p><div class="field" style="margin-top:14px"><select class="sel" id="rjr"><option>Wrong angle for this persona</option><option>Claim needs a stronger source</option><option>Tone does not match the campaign</option><option>Prospect is not a fit</option><option>Other</option></select></div><div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="rjgo">Reject</button></div>`);
 $('#rjgo').onclick=()=>{const reason=$('#rjr').value;closeModal();run(()=>api.post('/approvals/'+id+'/decide',{decision:'reject',reason}),{ok:'Rejected. The reason is saved.',after:()=>{UI.sel.appr=null}})};
};
ACT.reassign=t=>{const id=idOf(t),kind=t.dataset.t;const x=kind==='esc'?S.escal.find(v=>v.id===id):S.approvals.find(v=>v.id===id);const e=E(x.eid);const reps=S.users.filter(u=>u.role==='Rep'&&u.active);
 openModal(`<h2>Reassign to a rep</h2><div class="field" style="margin-top:14px"><label for="rsr">Rep</label><select class="sel" id="rsr">${reps.map(u=>`<option value="${u.id}" ${u.id===(e.rep||C(e.cid).reps[0])?'selected':''}>${esc(u.name)} (${u.label})</option>`).join('')}</select></div><div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="rsgo">Reassign</button></div>`);
 $('#rsgo').onclick=()=>{const rep=$('#rsr').value;closeModal();run(()=>kind==='esc'?api.post('/escalations/'+id+'/reassign',{replacement_rep_id:rep}):api.post('/enrollments/'+e.id+'/reassign',{replacement_rep_id:rep}),{ok:`Reassigned to ${U(rep).name}.`})};
};
ACT.escSend=t=>run(()=>api.post('/escalations/'+idOf(t)+'/resolve',{note:$('#escText').value}),{ok:'Reply sent and escalation resolved.',after:()=>{UI.sel.appr=null}});
ACT.giveTo=t=>{const x=S.conflicts.find(v=>v.id===idOf(t)),c=t.dataset.c;
 confirmBox('Override the conflict',`Give ${esc(P(x.pid).name)} to campaign ${c}? The other campaign stops contacting this person.`,'Give to '+c,()=>run(()=>api.post('/conflicts/'+x.id+'/resolve',{winner_campaign_id:c}),{ok:'Claim moved to '+c+'.',after:()=>{UI.sel.appr=null}}));
};

/* ---------- campaign controls ---------- */
ACT.pause=t=>{const id=idOf(t);run(()=>api.post('/campaigns/'+id+'/pause'),{optimistic:()=>{C(id).status='paused'},ok:r=>`${esc(C(id).name)} paused. ${r.held_jobs} jobs held. The other campaigns keep running.`,toast:{undo:()=>run(()=>api.post('/campaigns/'+id+'/resume'),{optimistic:()=>{C(id).status='live'}})}})};
ACT.resume=t=>{const id=idOf(t);run(()=>api.post('/campaigns/'+id+'/resume'),{optimistic:()=>{C(id).status='live'},ok:'Resumed. Held jobs continue.'})};
ACT.complete=t=>{const c=C(idOf(t));UI.menu=null;confirmBox('Complete this campaign',`${esc(c.name)} stops all activity and becomes read-only. Analytics stay available.`,'Complete campaign',()=>run(()=>api.post('/campaigns/'+c.id+'/complete'),{ok:'Campaign completed.'}))};
ACT.archive=t=>{const c=C(idOf(t));UI.menu=null;confirmBox('Archive this campaign',`${esc(c.name)} is hidden from the default list. Analytics stay available.`,'Archive',()=>run(()=>api.post('/campaigns/'+c.id+'/archive'),{ok:'Archived.',after:()=>go('/campaigns')}),true)};
ACT.campEdit=t=>{const c=C(idOf(t));if(!c)return;const list=v=>(v||[]).join(', ');
 openModal(`<h2>Edit ${esc(c.name)}</h2><p class="muted" style="margin:6px 0 14px">Saved as a new campaign version. Agents pick it up on their next step, and other campaigns are not affected.</p>
 <div class="col gap12"><div class="field"><label>Name</label><input class="inp" id="ce1" value="${esc(c.name)}"></div>
 <div class="field"><label>Objective</label><textarea class="txt" id="ce2" rows="2">${esc(c.objective)}</textarea></div>
 <div class="field"><label>ICP summary</label><input class="inp" id="ce3" value="${esc(c.icp)}"></div>
 <div class="grid g2"><div class="field"><label>Target roles (comma separated)</label><input class="inp" id="ce4" value="${esc(list(c.roles))}"></div><div class="field"><label>Geographies</label><input class="inp" id="ce5" value="${esc(list(c.geoList))}"></div></div>
 <div class="field"><label>Exclusions</label><input class="inp" id="ce6" value="${esc(list(c.exclusions))}"></div>
 <div class="field"><label>Tone</label><input class="inp" id="ce7" value="${esc(c.tone||'')}"></div>
 <div class="grid g2"><div class="field"><label>Qualification threshold (0 to 100)</label><input class="inp" id="ce8" type="number" min="0" max="100" value="${c.thr}"></div><div class="field"><label>Daily send cap</label><input class="inp" id="ce9" type="number" min="0" value="${c.cap}"></div></div></div>
 <div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="cego">Save changes</button></div>`,'lg');
 $('#cego').onclick=async()=>{const split=s=>s.split(',').map(x=>x.trim()).filter(Boolean),name=$('#ce1').value.trim(),thr=+$('#ce8').value,cap=+$('#ce9').value;
  if(!name){toast('Give the campaign a name.',{bad:true});return}
  if(!(thr>=0&&thr<=100)||!(cap>=0)){toast('Threshold is 0 to 100 and the daily cap cannot be negative.',{bad:true});return}
  try{const r=await api.patch('/campaigns/'+c.id,{name,objective:$('#ce2').value.trim(),icp:$('#ce3').value.trim(),roles:split($('#ce4').value),geo_list:split($('#ce5').value),exclusions:split($('#ce6').value),tone:$('#ce7').value.trim(),thr,daily_send_cap:cap});
   closeModal();await hydrate(true);repaint();toast(`${name} saved as version ${r.version}.`)}catch(e){toast(e.message,{bad:true})}}};
ACT.dup=t=>{UI.menu=null;run(()=>api.post('/campaigns/'+idOf(t)+'/duplicate',{}),{ok:r=>`Created ${esc(r.name)} as a Draft. Copy of prompts, settings and knowledge.`,after:r=>go('/campaigns/'+r.id+'/overview')})};
ACT.agentSw=t=>run(()=>api.put('/campaigns/'+idOf(t)+'/agents/'+t.dataset.k,{enabled:!C(idOf(t)).agents[t.dataset.k]}));
ACT.chanSw=t=>{const id=idOf(t),k=t.dataset.k;run(()=>api.put('/campaigns/'+id+'/channels/'+k,{enabled:!C(id).channels[k]}),{ok:r=>r.replanned?`Replanned ${r.replanned} prospect${r.replanned===1?'':'s'}: ${CH[k].n} paused, touches moved to email. Open a prospect to see the new plan.`:null,toast:{}}).then(()=>{})};
ACT.activate=async t=>{
 try{await api.post('/campaigns/'+idOf(t)+'/activate');await hydrate(true);toast(`${esc(C(idOf(t)).name)} is Live.`);repaint()}
 catch(e){toast(e.detail&&e.detail.checks?'The checklist has failing items: '+e.detail.checks.filter(x=>!x.passed).map(x=>x.name).join(', '):e.message,{bad:true})}
};
ACT.trySend=async t=>{
 const c=C(idOf(t)),e=S.enr.find(x=>x.cid===c.id);
 if(!e){toast('Add a prospect first.',{bad:true});return}
 try{await api.post('/outreach/send',{enrollment_id:e.id,channel:'email'});toast('The Guardian allowed the send.')}
 catch(err){
  if(err.status===409&&err.detail&&err.detail.gate){
   openModal(`<h2>Send refused</h2><p class="muted" style="margin:6px 0 14px">${esc(P(e.pid).name)}: the Guardian checked ${esc(c.name)} and stopped the send.</p><div class="banner bad" style="margin-bottom:12px">${ic('stop',16)}<span>Reason: <b class="mono">${esc(err.code)}</b></span></div>${gateView({cks:err.detail.gate})}<div class="mf"><button class="btn pri" data-a="closeModal">Close</button></div>`,'lg');
  }else toast(err.message,{bad:true});
 }
};
ACT.discover=t=>run(()=>api.post('/campaigns/'+idOf(t)+'/discover',{count:5}),{ok:r=>r.enrolled_ids.length?`Discovery added ${r.enrolled_ids.length} prospects to ${esc(C(idOf(t)).name)}. ${C(idOf(t)).status==='live'?'The agents start researching now.':'They wait until you activate the campaign.'}`:'No more demo prospects match this campaign.'});
ACT.discoverAny=t=>{
 const cid=idOf(t);
 if(cid){ACT.discover({dataset:{id:cid}});return}
 const live=S.camps.filter(c=>c.status==='live'||c.status==='draft');
 openModal(`<h2>Simulate discovery</h2><p class="muted" style="margin:6px 0 12px">Adds five demo prospects to a campaign, the way the lead source would.</p><div class="field"><select class="sel" id="dcs">${live.map(c=>`<option value="${c.id}">${c.id} ${esc(c.name)} (${c.status})</option>`).join('')}</select></div><div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="dcg">Add prospects</button></div>`);
 $('#dcg').onclick=()=>{const id=$('#dcs').value;closeModal();ACT.discover({dataset:{id}})};
};
ACT.importCsv=t=>{openModal(`<h2>Import prospects from CSV</h2><p class="muted" style="margin:6px 0 12px">One prospect per line: full name, title, company, then optionally email, phone and LinkedIn profile URL. Anything left out is generated for the sandbox.</p><textarea class="txt code" id="csvt" style="min-height:140px" placeholder="Jane Doe, CTO, Acme Labs">Jordan Ellis, CTO, Larkspur Systems\nMaya Brandt, VP Engineering, Tidewater Cloud</textarea><div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="csvgo" data-id="${idOf(t)}">Import</button></div>`);
 $('#csvgo').onclick=()=>{const text=$('#csvt').value;if(!text.trim().split('\n').some(l=>l.split(',').length>=3)){toast('Add at least one line with a name, title and company.',{bad:true});return}
  closeModal();run(()=>api.post('/campaigns/'+idOf(t)+'/prospects/import',{text}),{ok:r=>`Imported ${r.created} prospects${r.deduped?`, ${r.deduped} already there`:''}.`})};
};

/* ---------- create campaign ---------- */
function cfBody(){
 const cf=UI.cf,split=s=>s.split(',').map(x=>x.trim()).filter(Boolean);
 return{name:cf.name.trim(),objective:cf.objective,icp:cf.size||cf.name,roles:split(cf.roles),geo_list:split(cf.geo),exclusions:split(cf.exclusions),refs:cf.refs,tone:cf.tone,thr:+cf.thr||70,daily_send_cap:+cf.cap||0,
  first:!!cf.first,voice:!!cf.voice,reply:!!cf.reply,channels:cf.channels,agents:cf.agents,rep_ids:cf.reps,doc_ids:cf.docs,tpl:cf.tpl||'C1'};
}
async function cfSave(){
 const cf=UI.cf;
 if(!cf.name.trim()){toast('Give the campaign a name first.',{bad:true});return null}
 if(cf.id){const b=cfBody();delete b.name;delete b.first;delete b.voice;delete b.reply;delete b.channels;delete b.agents;delete b.tpl;
  await api.patch('/campaigns/'+cf.id,Object.assign(b,{name:cf.name.trim(),appr:{first:!!cf.first,voice:!!cf.voice,reply:!!cf.reply}}));}
 else{const r=await api.post('/campaigns',cfBody());cf.id=r.id}
 await hydrate(true);
 return cf.id;
}
ACT.cfSave=async()=>{try{const id=await cfSave();if(id){toast('Saved as a Draft.');go('/campaigns/'+id+'/overview')}}catch(e){toast(e.message,{bad:true})}};
ACT.dryNow=async t=>{const id=idOf(t);if((UI.dry||{})[id])return;UI.dry=Object.assign(UI.dry||{},{[id]:true});repaint();toast('Running the dry run on 3 sample prospects. This can take up to a minute.');
 try{const r=await api.post('/campaigns/'+id+'/dry-run');UI.dry[id]=false;await hydrate(true);repaint();
  if(r.grounding_passed){toast('Dry run passed. Every claim in the 3 samples has evidence.');return}
  const bad=(r.results||[]).filter(x=>!x.ok);
  openModal(`<h2>The dry run did not pass</h2><p class="muted" style="margin:6px 0 12px">Nothing was stored or sent. Fix this and run it again.</p><div class="col gap8">${bad.map(x=>`<div class="banner bad" style="font-weight:450">${esc(x.agent)}: ${esc(x.output_summary)}</div>`).join('')||'<div class="banner bad">The grounding check failed.</div>'}</div><div class="mf"><button class="btn pri" data-a="closeModal">Close</button></div>`)
 }catch(e){UI.dry[id]=false;repaint();toast(e.message,{bad:true})}};
ACT.cfActivate=async()=>{
 if(!cfCk(UI.cf).every(x=>x.ok)){toast('Finish the checklist first.',{bad:true});return}
 try{const id=await cfSave();if(!id)return;await api.post('/campaigns/'+id+'/activate');UI.cf=null;await hydrate(true);toast('Campaign is Live. Add prospects with Simulate discovery.');go('/campaigns/'+id+'/overview')}
 catch(e){toast(e.detail&&e.detail.checks?'The checklist has failing items: '+e.detail.checks.filter(x=>!x.passed).map(x=>x.name).join(', '):e.message,{bad:true})}
};
ACT.cfDry=async()=>{
 const cf=UI.cf,ck=cfCk(cf);
 if(!cf.name.trim()){toast('Name the campaign before the dry run.',{bad:true});return}
 if(ck.slice(0,5).some(x=>!x.ok)){cf.dry={done:true,ok:false,agent:'Setup',msg:'finish the first five checklist items so the samples have a full harness',key:''};refreshCk();return}
 cf.dry={run:true,i:1};refreshCk();
 try{
  const id=await cfSave();const r=await api.post('/campaigns/'+id+'/dry-run');
  const bad=(r.results||[]).find(x=>!x.ok);
  cf.dry={done:true,ok:!!r.grounding_passed,key:JSON.stringify([cf.tpl,cf.roles,cf.geo,cf.exclusions,cf.tone,cf.docs,cf.channels]),sample:r.sample||'',agent:bad?bad.agent:'',msg:bad?bad.output_summary:''};
 }catch(e){cf.dry={done:true,ok:false,agent:'Setup',msg:e.message,key:''}}
 refreshCk();
};

/* ---------- prospects ---------- */
ACT.stopP=t=>{const e=E(idOf(t));confirmBox('Stop this prospect',`${esc(P(e.pid).name)} leaves the ${esc(C(e.cid).name)} sequence. Pending touches are cancelled and the claim is released.`,'Stop prospect',()=>run(()=>api.post('/enrollments/'+e.id+'/stop',{reason:'Stopped by a person'}),{ok:'Prospect stopped.'}),true)};
ACT.escalateMan=t=>run(()=>api.post('/enrollments/'+idOf(t)+'/escalate'),{ok:'Escalated. It is in the Escalations tab.'});
ACT.runNow=t=>run(()=>api.post('/enrollments/'+idOf(t)+'/run',{step:'research'}),{ok:'Queued. The agents pick this prospect up now. Watch the timeline below.'});
ACT.simReply=t=>{
 const e=E(idOf(t)),p=P(e.pid),k=TK(e.cid);const obj={C1:'We are building this in-house.',C2:'Where does customer data stay?',C3:'We already use a competitor.',C4:'We use it less than we planned.'}[k]||'We are building this in-house.';
 const pre=[['Interested, tell me more.','Positive'],['The first slot works for me.','Accepts slot'],[obj,'Objection'],['Not now, revisit in Q1.','Not now'],['Can you do a 30% volume discount?','Pricing (escalates)'],['Send your SOC 2 report and security questionnaire.','Security (escalates)'],['Unsubscribe.','Opt-out']];
 const chs=Object.keys(CH).filter(c=>c!=='voice');
 openModal(`<h2>Simulate a reply from ${esc(p.first)}</h2><p class="muted" style="margin:6px 0 14px">Demo tool. The reply goes through the same inbound function that Gmail polling and the SMS webhook use, so the real classification and Guardian rules run.</p>
 <div class="row wrap">${pre.map(x=>`<button class="chip line" style="cursor:pointer;height:30px" data-a="presetR" data-t="${esc(x[0])}">${x[1]}</button>`).join('')}</div>
 <div class="field" style="margin-top:14px"><label>Reply text</label><textarea class="txt" id="srt" rows="3">${esc(pre[0][0])}</textarea></div>
 <div class="field" style="margin-top:12px"><label>Channel</label><select class="sel" id="src">${chs.map(c=>`<option value="${c}">${CH[c].n}</option>`).join('')}</select></div>
 <div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="srgo">Send reply</button></div>`);
 $('#srgo').onclick=()=>{const body=$('#srt').value.trim();if(!body)return;const channel=$('#src').value;closeModal();
  run(()=>api.post('/demo/simulate-reply',{enrollment_id:e.id,channel,body}),{ok:r=>`Classified as ${r.classification==='escalate'?ESC[r.sub]:String(r.classification).replace('_',' ')} by ${r.rule}. ${r.classification==='escalate'?'An escalation is open.':'The Responder answers next.'}`})};
};
ACT.liOpen=t=>{window.open('https://'+t.dataset.u.replace(/^https?:\/\//,''),'_blank','noopener')};
ACT.liCopy=async t=>{const et=$('#editText'),ap=S.approvals.find(v=>v.id===idOf(t)),v=et&&!$('#draftEdit').hidden?et.value:S.msgs.find(z=>z.id===ap.msgId).body;
 try{await navigator.clipboard.writeText(v.trim());toast('Note copied.')}catch(e){toast('Copy failed. Select the note and copy it by hand.',{bad:true})}};
ACT.liPaste=t=>{const e=E(idOf(t));openModal(`<h2>Paste a LinkedIn reply from ${esc(P(e.pid).first)}</h2><p class="muted" style="margin:6px 0 14px">Copy the reply from LinkedIn. It goes through the same inbound function as email and SMS replies, so the real classification and Guardian rules run.</p>
 <div class="field"><label>Reply text</label><textarea class="txt" id="lir" rows="4"></textarea></div>
 <div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="ligo">Record reply</button></div>`);
 $('#ligo').onclick=()=>{const text=$('#lir').value.trim();if(!text)return;closeModal();
  run(()=>api.post('/enrollments/'+e.id+'/linkedin-reply',{text}),{ok:r=>`Classified as ${r.classification==='escalate'?ESC[r.sub]:String(r.classification).replace('_',' ')} by ${r.rule}.`})}};
ACT.humanSend=t=>{const txt=$('#humanText').value.trim();if(!txt)return;run(()=>api.post('/enrollments/'+idOf(t)+'/reply',{text:txt}),{ok:'Reply sent as '+S.user.name+'.',after:()=>{UI.sel.take=null}})};

/* ---------- prompts ---------- */
ACT.prSave=async()=>{
 const txt=$('#prText').value,l=lintPrompt(txt);
 if(l.length){$('#prLint').innerHTML=l.map(x=>`<div class="banner bad" style="margin-top:6px;font-weight:450">${ic('alert',15)}${esc(x)}</div>`).join('');toast('Fix the lint errors before you save.',{bad:true});return}
 run(()=>api.post('/campaigns/'+UI.pr.cid+'/prompts',{agent_key:UI.pr.role,body:txt,note:'Edited by '+S.user.name,parent_version:UI.pr.v}),{ok:r=>`Saved as v${r.version}. Activate it when you are ready.`,after:r=>{UI.pr.v=r.version}});
};
ACT.prActivate=t=>{const v=+t.dataset.v,cid=UI.pr.cid,role=UI.pr.role;const q=S.jobs.filter(j=>j.cid===cid&&roleOf(j)===role&&j.status==='queued').length;
 confirmBox(`Activate ${role} v${v}`,`The next ${role} job uses v${v}. ${q} queued ${q===1?'job uses':'jobs use'} it. Running jobs finish on the old version.`,`Activate v${v}`,()=>run(()=>api.post('/prompts/'+cid+'-'+role+'-v'+v+'/activate'),{ok:`${role} v${v} is active.`}));
};
ACT.prRoll=()=>{const cid=UI.pr.cid,role=UI.pr.role;const vs=pver(cid,role);const cur=vs.find(x=>x.status==='active');const prev=vs.find(x=>x.v<cur.v);if(!prev)return;
 confirmBox(`Roll back ${role}`,`Go back to v${prev.v}. The change applies to the next job.`,`Roll back to v${prev.v}`,()=>run(()=>api.post('/prompts/'+cid+'-'+role+'-v'+prev.v+'/activate',{rollback:true}),{ok:`Rolled back to v${prev.v}.`,after:()=>{UI.pr.v=prev.v}}));
};
ACT.prGold=async()=>{
 const cid=UI.pr.cid,role=UI.pr.role;
 try{const r=await api.post('/campaigns/'+cid+'/prompts/'+encodeURIComponent(role)+'/golden',{version:UI.pr.v});await hydrate(true);toast(`Golden set: ${r.score}% (${r.passed} of ${r.total} cases, ${r.method}).`);repaint()}
 catch(e){toast(e.message,{bad:true})}
};
ACT.prCoach=async()=>{
 const cid=UI.pr.cid,role=UI.pr.role;
 try{const r=await api.post('/campaigns/'+cid+'/prompts/'+encodeURIComponent(role)+'/coach',{version:UI.pr.v});await hydrate(true);UI.pr.v=r.version;
  toast(`The coach drafted v${r.version} from ${r.failing} failing golden cases. Review the diff, replay it, then activate.`);repaint()}
 catch(e){$('#prCoachOut').innerHTML=`<div class="banner mist" style="margin-top:14px;font-weight:450">${ic('info',16)}<span>${esc(e.message)}</span></div>`}
};

/* ---------- knowledge ---------- */
ACT.kbRe=t=>run(()=>api.post('/knowledge/documents/'+idOf(t)+'/reingest'),{ok:r=>`Re-ingested: ${r.chunks} chunks embedded.`});
ACT.kbDel=t=>{const d=S.kb.docs.find(x=>x.id===idOf(t));confirmBox('Delete this document',`${esc(d.name)} (${d.chunks.length} chunks) leaves the knowledge base. Agents can no longer cite it. Past messages keep their citations.`,'Delete document',()=>run(()=>api.del('/knowledge/documents/'+d.id),{ok:'Document deleted.'}),true)};
ACT.kbSearch=async t=>{const q=$('#kq').value.trim();UI.kq=q;if(!q){UI.kres=null;repaint();return}
 try{const r=await api.post('/knowledge/search',{campaign_id:t.dataset.c,query:q,k:4});UI.kres=r.map(x=>({id:x.id,doc:x.label,text:x.text,s:x.score}));repaint()}
 catch(e){toast(e.message,{bad:true})}
};
ACT.kbUp=t=>{
 const cid=(t&&t.dataset)?t.dataset.c:'';
 const camps=S.camps||[];
 const scopeOpts=[
  `<option value="global" ${!cid||cid==='global'?'selected':''}>Global (all campaigns)</option>`,
  ...camps.map(x=>`<option value="${x.id}" ${x.id===cid?'selected':''}>${x.id} - ${esc(x.name)}</option>`)
 ].join('');
 openModal(`<h2>Upload a document</h2><div class="col gap12" style="margin-top:14px"><div class="field"><label>Choose file (optional: .txt, .md, .csv, .json)</label><input class="inp" type="file" id="ku0" accept=".txt,.md,.markdown,.json,.csv,.text"></div><div class="field"><label>Title</label><input class="inp" id="ku1" placeholder="Case study: Acme"></div><div class="grid g2"><div class="field"><label>Type</label><select class="sel" id="ku2"><option value="case study">case study</option><option value="objections">objections</option><option value="icp">icp</option><option value="playbook">playbook</option><option value="pricing">pricing</option><option value="brand">brand</option></select></div><div class="field"><label>Scope</label><select class="sel" id="ku3">${scopeOpts}</select></div></div><div class="field"><label>Text (separate chunks with a blank line)</label><textarea class="txt" id="ku4" rows="6" placeholder="Paste markdown or plain text, or select a file above"></textarea></div></div><div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="kugo">Upload and ingest</button></div>`);
 const fi=$('#ku0');
 if(fi){
  fi.onchange=e=>{
   const f=e.target.files&&e.target.files[0];
   if(!f)return;
   const ti=$('#ku1');
   if(ti&&!ti.value.trim()){ti.value=f.name.replace(/\.[^/.]+$/,'')}
   const r=new FileReader();
   r.onload=ev=>{const tx=$('#ku4');if(tx)tx.value=ev.target.result};
   r.readAsText(f);
  };
 }
 $('#kugo').onclick=()=>{
  const name=$('#ku1').value.trim(),text=$('#ku4').value.trim();
  if(!name||!text){toast('Add a title and some text, or select a file.',{bad:true});return}
  const scope=$('#ku3').value||'global';
  const doc_type=$('#ku2').value||'case study';
  closeModal();
  run(()=>api.post('/knowledge/documents',{name,doc_type,scope,text}),{ok:r=>`Ingested ${esc(name)} as ${r.chunks.length} chunks.`});
 };
};

/* ---------- settings ---------- */
ACT.integSw=t=>{const v=S.integ[t.dataset.k];run(()=>api.post('/integrations/'+t.dataset.k+'/pause',{paused:!v.paused}),{ok:r=>v.paused?`${v.n} resumed.`:`${v.n} paused everywhere.${r.replanned?` Replanned ${r.replanned} prospects.`:''}`})};
ACT.integMode=t=>{const v=S.integ[t.dataset.k];run(()=>api.post('/integrations/'+t.dataset.k+'/mode',{mode:t.dataset.m}),{ok:`${v.n} is now ${t.dataset.m.toUpperCase()}. New messages carry the ${t.dataset.m.toUpperCase()} tag.`})};
ACT.integTest=async t=>{const v=S.integ[t.dataset.k];try{const r=await api.post('/integrations/'+t.dataset.k+'/test');await hydrate(true);r.ok?toast(`${v.n} responded.`):toast(`${v.n} still fails: ${r.error}`,{bad:true});repaint()}catch(e){toast(e.message,{bad:true})}};
ACT.repAdd=()=>{openModal(`<h2>Add a user</h2><div class="col gap12" style="margin-top:14px"><div class="field"><label>Full name</label><input class="inp" id="ra1"></div><div class="field"><label>Role</label><select class="sel" id="ra4"><option value="Rep">Rep</option><option value="Manager">Manager</option><option value="Admin">Admin</option></select></div><div class="field"><label>Email (optional)</label><input class="inp" id="ra5" type="email" placeholder="Leave blank for name@helix.demo"></div><div class="field" id="ra2f"><label>Daily send limit (reps)</label><input class="inp" id="ra2" type="number" value="30"></div></div><div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="ra3">Add user</button></div>`);
 $('#ra4').onchange=()=>{$('#ra2f').hidden=$('#ra4').value!=='Rep'};
 $('#ra3').onclick=async()=>{const n=$('#ra1').value.trim();if(!n){toast('Enter a name.',{bad:true});return}
  try{const r=await api.post('/users',{name:n,role:$('#ra4').value,email:$('#ra5').value.trim()||null,rep_limit:+$('#ra2').value||30});await hydrate(true);
   openModal(`<h2>${esc(n)} was added</h2><p class="muted" style="margin:6px 0 14px">Share these sign-in details now. The password is shown once and is not stored anywhere you can read it.</p><div class="pre">Email: ${esc(r.email)}
Role: ${esc(r.role)}
Password: ${esc(r.password)}</div><div class="mf"><button class="btn" data-a="closeModal">Done</button></div>`);repaint()}
  catch(e){toast(e.message,{bad:true})}};
};
ACT.pwOpen=()=>{openModal(`<h2>Change your password</h2><div class="col gap12" style="margin-top:14px"><div class="field"><label>Current password</label><input class="inp" id="pw1" type="password" autocomplete="current-password"></div><div class="field"><label>New password (8 characters or more)</label><input class="inp" id="pw2" type="password" autocomplete="new-password"></div></div><div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="pw3">Change password</button></div>`);
 $('#pw3').onclick=async()=>{const cur=$('#pw1').value,nw=$('#pw2').value;if(nw.length<8){toast('Use at least 8 characters.',{bad:true});return}
  try{await api.post('/auth/password',{current:cur,new:nw});closeModal();toast('Password changed.')}catch(e){toast(e.message,{bad:true})}};
};
ACT.repOff=async t=>{
 const u=U(idOf(t));let aff;
 try{aff=(await api.get('/reps/'+u.id+'/affected')).affected}catch(e){toast(e.message,{bad:true});return}
 const others=S.users.filter(x=>x.role==='Rep'&&x.active&&x.id!==u.id);
 openModal(`<h2>Offboard ${esc(u.name)}</h2><p class="muted" style="margin:6px 0 10px">This affects ${aff.campaigns.length} campaign${aff.campaigns.length===1?'':'s'}, ${aff.enrollments} open prospects and ${aff.open_escalations} open escalations. Pick who takes them, or leave them unassigned to see the no_rep_available alert.</p><div class="row wrap" style="margin-bottom:12px">${aff.campaigns.map(c=>campChip(c,true)).join('')||'<span class="faint">No campaigns</span>'}</div><div class="field"><select class="sel" id="ro1">${others.map(x=>`<option value="${x.id}">${esc(x.name)} (${x.label})</option>`).join('')}<option value="">Nobody</option></select></div><div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn dan" id="ro2">Offboard</button></div>`);
 $('#ro2').onclick=()=>{const to=$('#ro1').value;closeModal();run(()=>api.post('/reps/'+u.id+'/offboard',{replacement_rep_id:to||null}),{ok:to?`Offboarded. Items moved to ${U(to).name}.`:'Offboarded. Campaigns without a rep now alert on Command Center.'})};
};
ACT.repDel=async t=>{
 const u=U(idOf(t));let aff;
 try{aff=(await api.get('/reps/'+u.id+'/affected')).affected}catch(e){toast(e.message,{bad:true});return}
 const work=aff.campaigns.length||aff.enrollments||aff.open_escalations;
 const others=S.users.filter(x=>x.role==='Rep'&&x.active&&x.id!==u.id);
 if(work&&!others.length){toast('This rep still holds work and there is no other active rep to take it. Add a rep first.',{bad:true});return}
 openModal(`<h2>Delete ${esc(u.name)}</h2><p class="muted" style="margin:6px 0 10px">${work?`This rep holds ${aff.campaigns.length} campaign${aff.campaigns.length===1?'':'s'}, ${aff.enrollments} open prospects and ${aff.open_escalations} open escalations. Pick who takes them over.`:'This rep holds no work.'} The account is removed and cannot sign in again. If past records refer to them, the account is kept as offboarded so the history still shows who handled it.</p>${work?`<div class="field"><select class="sel" id="rd1">${others.map(x=>`<option value="${x.id}">${esc(x.name)} (${x.label})</option>`).join('')}</select></div>`:''}<div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="rd2" style="background:var(--bad,#b3261e);border-color:transparent">Delete rep</button></div>`);
 $('#rd2').onclick=()=>{const to=work?$('#rd1').value:'';closeModal();run(()=>api.del('/reps/'+u.id+(to?'?replacement_rep_id='+encodeURIComponent(to):'')),{ok:r=>r.deleted?`${u.name} deleted.`:`${u.name} kept as offboarded because past records refer to them.`})};
};
ACT.supAdd=()=>{const v=$('#sup2').value.trim();if(!v){toast('Enter an address, domain or number.',{bad:true});return}run(()=>api.post('/suppression',{kind:$('#sup1').value,value:v,reason:$('#sup3').value||'Added by hand'}),{ok:'Added to the suppression list.'})};
ACT.supDel=t=>{const x=S.suppress.find(v=>v.id===idOf(t));confirmBox('Remove from suppression',`${esc(x.value)} can be contacted again after this. Only do this when the person asked you to.`,'Remove',()=>run(()=>api.del('/suppression/'+x.id),{ok:'Removed.'}),true)};
ACT.adv=t=>run(()=>api.post('/demo/advance-clock',{hours:+t.dataset.h}),{ok:`Clock moved forward ${t.dataset.h} hours. The agents are working through what came due.`});
ACT.playCall=()=>{
 const cands=S.enr.filter(e=>C(e.cid).channels.voice&&['replied_pos','awaiting_voice','contacted','qualified'].includes(e.st));
 openModal(`<h2>Play a scripted call outcome</h2><p class="muted" style="margin:6px 0 12px">Runs the DronaHQ Voice post-call path with a scripted transcript. The call is labelled SANDBOX. Use it when telephony is unavailable.</p><div class="field"><select class="sel" id="pcs">${cands.map(e=>`<option value="${e.id}">${esc(P(e.pid).name)} (${e.cid})</option>`).join('')||'<option value="">No prospect in a voice campaign</option>'}</select></div><div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn pri" id="pcg">Play outcome</button></div>`);
 $('#pcg').onclick=()=>{const id=$('#pcs').value;if(!id)return;closeModal();run(()=>api.post('/demo/play-call',{enrollment_id:id}),{ok:'Scripted call outcome recorded. The transcript is in the thread.'})};
};
ACT.reset=()=>confirmBox('Reset demo data','This rebuilds the seeded workspace. Every change you made goes away.','Reset data',()=>run(()=>api.post('/demo/reset'),{ok:'Demo data reset.',after:()=>{UI.cf=null;UI.sel={};UI.fil={};go('/overview')}}),true);

/* ---------- campaign config fields ---------- */
function cfgPatch(el){
 const c=C(el.dataset.id),f=el.dataset.f,v=el.value,b={};
 if(f==='cap')b.daily_send_cap=+v;else if(f==='thr')b.thr=+v;else if(f==='priority')b.priority=+v;
 else if(f.startsWith('lim_'))b.ch_limit={[f.slice(4)]:+v};else if(f.startsWith('appr_'))b.appr={[f.slice(5)]:v==='1'};
 return{c,b};
}
