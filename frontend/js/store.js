/* Client state. S mirrors GET /state. Everything here reads S and never changes it. */
let S=null;
const C=id=>S.camps.find(c=>c.id===id);
const P=id=>S.people[id];
const E=id=>S.enrById[id];
const U=id=>S.users.find(u=>u.id===id);
const cc=id=>COLORS[id]||'cx';
const TK=cid=>{const c=S&&S.camps&&S.camps.find(x=>x.id===cid);return c&&c.tpl||cid};
const enrOf=pid=>S.enr.filter(e=>e.pid===pid);
const msgsOf=e=>S.msgs.filter(m=>m.eid===e.id);
const hash=s=>{let h=7;for(const ch of s)h=(h*31+ch.charCodeAt(0))|0;return Math.abs(h)};

function chanMode(ch){const m={email:S.integ.gmail.mode,linkedin:S.integ.linkedin.mode,sms:S.integ.twilio.mode,voice:S.integ.voice.mode};return m[ch]||'sandbox'}
const meU=()=>S.user;
function E0(pid,cid){return S.enr.find(x=>x.pid===pid&&x.cid===cid)}
function jobState(j){
 if(j.status!=='queued')return j.status;
 const c=C(j.cid);
 if(S.kill)return'held';if(c.status!=='live')return'held';if(!c.agents[j.agent])return'held';
 if(j.due>S.now)return'scheduled';
 return'queued';
}
function heldReason(j){const c=C(j.cid);if(S.kill)return'kill_switch';if(c.status==='paused')return'campaign_paused';if(c.status!=='live')return'campaign_not_live';if(!c.agents[j.agent])return'agent_paused';return''}
function heldCount(cid){return S.jobs.filter(j=>(!cid||j.cid===cid)&&j.status==='queued'&&jobState(j)==='held').length}
function roleOf(j){return {Researcher:'Researcher',Qualifier:'Qualifier',Sequencer:'Strategy',Writer:'Writer',Responder:'Responder',Caller:'Caller'}[j.agent]}
function repFor(e){return U(e.rep||C(e.cid).reps[0])||{id:null,name:'Unassigned',active:false,limit:0,channels:[],label:'',hours:'',tz:'PT'}}
function gateView(g){return g.cks.map(k=>`<div class="check ${k.ok?'ok':'no'}"><span class="b">${k.ok?ic('check',12):''}</span><div><b>${k.n}. ${k.code}</b><div class="small muted">${esc(k.note)}</div></div></div>`).join('')}
/* ---------- stats ---------- */
function enrIn(cid){return S.enr.filter(e=>e.cid===cid)}
function funnel(cid){const es=enrIn(cid);return STAGES.map((s,i)=>({s,n:es.filter(e=>(STATE[e.st]||STATE.new).st>=i&&!(e.st==='new'&&i>0)).length}))}
function outMsgs(cid,since){return S.msgs.filter(m=>m.dir==='out'&&m.status==='sent'&&!m.reply&&m.kind!=='call'&&(cid?m.cid===cid:1)&&(since?m.t>=since:1))}
function inMsgs(cid,since){return S.msgs.filter(m=>m.dir==='in'&&(cid?m.cid===cid:1)&&(since?m.t>=since:1))}
function runCost(cid,since){return S.jobs.filter(j=>j.status==='done'&&!j.replay&&(cid?j.cid===cid:1)&&(since?j.at>=since:1)).reduce((a,j)=>a+(j.cost||0),0)}
function cstats(cid,since){
 const es=enrIn(cid),out=outMsgs(cid,since),inn=inMsgs(cid,since);
 const repliedEnr=new Set(inn.map(m=>m.eid));const pos=new Set(inn.filter(m=>['positive','book'].includes(m.cls)).map(m=>m.eid));
 const touched=new Set(out.map(m=>m.eid));
 const q=es.filter(e=>(STATE[e.st]||STATE.new).st>=2||['borderline'].includes(e.st)&&0).length;
 const meet=S.meetings.filter(m=>m.cid===cid).length;
 const cost=runCost(cid,since);
 return{prospects:es.length,touches:out.length,contacted:touched.size,replies:repliedEnr.size,pos:pos.size,meetings:meet,qualified:q,cost,
  replyRate:touched.size?repliedEnr.size/touched.size:0,posRate:touched.size?pos.size/touched.size:0,meetRate:touched.size?meet/touched.size:0,
  cpql:q?cost/q:0,cpc:repliedEnr.size?cost/repliedEnr.size:0};
}
function needsYou(){
 const me=meU();const vis=c=>me.role!=='Rep'||C(c).reps.includes(me.id);
 return{appr:S.approvals.filter(a=>a.status==='open'&&vis(a.cid)),esc:S.escal.filter(x=>x.status==='open'&&(me.role!=='Rep'||x.rep===me.id)),conf:S.conflicts.filter(x=>x.status==='open'&&me.role!=='Rep')};
}
function needsCount(){const n=needsYou();return n.appr.length+n.esc.length+n.conf.length}
function alerts(){
 const a=[];
 S.camps.filter(c=>c.status==='paused').forEach(c=>a.push({t:'warn',ic:'pause',x:`${c.name} is paused. ${heldCount(c.id)} jobs held.`,go:'#/campaigns/'+c.id+'/overview'}));
 S.camps.forEach(c=>{Object.keys(c.agents).forEach(k=>{if(!c.agents[k]&&c.status!=='draft')a.push({t:'warn',ic:'pause',x:`${k} is off for ${c.name}. Jobs wait on the paused agent.`,go:'#/campaigns/'+c.id+'/activity'})});
  if(c.status==='live'&&!c.reps.some(r=>U(r).active))a.push({t:'bad',ic:'alert',x:`${c.name} has no active rep. Sends defer with no_rep_available.`,go:'#/settings/reps'})});
 Object.entries(S.integ).forEach(([k,v])=>{if(v.status==='error')a.push({t:'bad',ic:'alert',x:`${v.n} is in error: ${v.err}`,go:'#/settings/integrations'})});
 const f=S.jobs.filter(j=>j.status==='failed').length;if(f)a.push({t:'bad',ic:'alert',x:`${f} failed job${f===1?'':'s'} need a retry.`,go:'#/activity'});
 return a;
}
