/* Screens and shared UI. Data comes from store.js, changes go through actions.js. */
/* ---------- UI framework ---------- */
const UI={path:'/overview',q:'',fil:{},tab:{},sel:{},cf:null,menu:null,keep:false};
const ACT={};
const av=(name,cls,on)=>`<span class="avatar ${cls||''} a${hash(name)%6}${on?' on':''}" title="${esc(name)}">${esc(initials(name))}</span>`;
const campChip=(cid,full)=>{const c=C(cid);return c?`<span class="chip ${cc(cid)}"><i class="dot ${cc(cid)}"></i>${cid}${full?' '+esc(c.name):''}</span>`:''};
function statusPill(c){const s=c.status;
 if(s==='live')return`<span class="pill live"><i class="dot live"></i>Live</span>`;
 if(s==='paused')return`<span class="pill paused">${ic('pause',12)}Paused</span>`;
 if(s==='draft')return`<span class="pill draft">${ic('edit',12)}Draft</span>`;
 return`<span class="pill done">${ic('check',12)}${cap(s)}</span>`}
const modeTag=m=>m==='live'?'<span class="tag live">LIVE</span>':m==='replay'?'<span class="tag replay">REPLAY</span>':'<span class="tag sbx">SANDBOX</span>';
const demoTag='<span class="tag demo">DEMO</span>';
const scoreBar=(s,e)=>s==null?`<span class="faint">${e&&e.st==='rejected'?'Rule reject':'-'}</span>`:`<div class="row gap4" style="min-width:96px"><div class="bar grow ${s>=70?'g':''}"><i style="width:${s}%"></i></div><b style="font-weight:550;width:24px">${s}</b></div>`;
const chIc=ch=>ic((CH[ch]||{}).i||'msg',15);
const empty=(t,d,btn)=>`<div class="empty"><b>${t}</b>${d}${btn||''}</div>`;
const sw=(on,a,attrs,dis)=>`<button class="switch ${on?'on':''}" role="switch" aria-checked="${!!on}" data-a="${a}" ${attrs||''} ${dis?'disabled':''}></button>`;
const tabs=(items,cur,a)=>`<div class="tabs">${items.map(t=>`<button class="${t.k===cur?'on':''}" data-a="${a}" data-k="${t.k}">${t.l}${t.n!=null?`<span class="cnt">${t.n}</span>`:''}</button>`).join('')}</div>`;
function nextAction(e){
 const p=P(e.pid);
 if(e.st==='new')return{t:'Research',w:'queued',x:'Research (queued)'};
 if(e.st==='researched')return{t:'Qualify',x:'Qualify (queued)'};
 if(['awaiting_approval','awaiting_voice','borderline'].includes(e.st))return{t:'Approval',x:e.st==='borderline'?'Manager review':'Waiting for approval'};
 if(e.st==='escalated')return{t:'Rep',x:'Rep reply ('+first(repFor(e).name)+')'};
 if(['meeting'].includes(e.st))return{t:'Meeting',x:e.meeting?'Meeting '+(e.meeting.label||fDT(e.meeting.at)):'Meeting booked'};
 if(['rejected','opted_out','stopped'].includes(e.st))return{t:'None',x:'None'};
 if(e.st==='deferred')return{t:'Wait',x:'Waiting on claim'};
 if(e.st==='replied_notnow')return{t:'Wake',x:'Wake '+fD(e.wake||S.now+90*D)};
 if(['replied_pos','replied_obj'].includes(e.st))return{t:'Reply',x:'Awaiting prospect'};
 const s=(e.plan||[]).find(x=>x.status==='pending');
 if(s)return{t:CH[s.ch].n,at:s.due,x:`${CH[s.ch].n} ${s.purpose.replace('_',' ')} ${rel(s.due)}`};
 return{t:'None',x:'None'};
}
/* ---------- charts ---------- */
function barsHatched(days,w,h){
 const max=Math.max(5,...days.flatMap(d=>[d.a,d.b]));const top=Math.ceil(max/5)*5;const pad=24,bw=Math.floor((w-pad-6)/(days.length*2+days.length))||10;
 let s=`<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="Touches sent and replies received per day"><defs><pattern id="hp" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="#f6f7ee"/><line x1="0" y1="0" x2="0" y2="5" stroke="#1f201d" stroke-width="2"/></pattern></defs>`;
 [0,top/2,top].forEach(v=>{const y=h-18-(v/top)*(h-30);s+=`<text x="0" y="${y+4}" font-size="11" fill="#8f9088">${v}</text>`});
 days.forEach((d,i)=>{const x=pad+i*(bw*3);const ha=(d.a/top)*(h-30),hb=(d.b/top)*(h-30);
  s+=`<rect x="${x}" y="${h-18-ha}" width="${bw}" height="${Math.max(ha,1)}" rx="3" fill="#1f201d"><title>${d.l}: ${d.a} touches sent</title></rect>`;
  s+=`<rect x="${x+bw+2}" y="${h-18-hb}" width="${bw}" height="${Math.max(hb,1)}" rx="3" fill="url(#hp)" stroke="#1f201d" stroke-width="1"><title>${d.l}: ${d.b} replies</title></rect>`;
  s+=`<text x="${x+bw}" y="${h-3}" font-size="11" text-anchor="middle" fill="#5d5e58">${d.l}</text>`});
 return s+'</svg>';
}
function gauge(p,label){
 const N=44,cx=120,cy=112,r1=88,r2=110;let s=`<svg viewBox="0 0 240 130" width="240" height="130" role="img" aria-label="${esc(label)} ${Math.round(p*100)} percent">`;
 for(let i=0;i<N;i++){const a=Math.PI+(Math.PI*i/(N-1));const on=i/(N-1)<=p;
  s+=`<line x1="${cx+Math.cos(a)*r1}" y1="${cy+Math.sin(a)*r1}" x2="${cx+Math.cos(a)*r2}" y2="${cy+Math.sin(a)*r2}" stroke="${on?'#1f201d':'#cfd0c4'}" stroke-width="2.2" stroke-linecap="round"/>`}
 s+=`<text x="${cx}" y="${cy-26}" font-size="34" font-weight="500" text-anchor="middle" fill="#1f201d" letter-spacing="-1">${Math.round(p*100)}%</text><text x="${cx}" y="${cy-4}" font-size="13" text-anchor="middle" fill="#5d5e58">${esc(label)}</text></svg>`;return s;
}
function spark(vals,w,h,color){
 if(!vals||vals.length<2)return`<span class="faint small">collecting</span>`;
 const mx=Math.max(1,...vals),st=w/(vals.length-1);
 const pts=vals.map((v,i)=>`${(i*st).toFixed(1)},${(h-2-(v/mx)*(h-4)).toFixed(1)}`).join(' ');
 return`<svg class="sparkline" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline fill="none" stroke="${color||'#1f201d'}" stroke-width="1.6" points="${pts}"/></svg>`;
}
function stagebar(f){const mx=Math.max(1,f[0].n);
 return`<div class="stagebar">${f.map((x,i)=>`<div class="r"><span>${x.s}</span><div class="bar"><i style="width:${Math.max(x.n?2:0,100*x.n/mx)}%"></i></div><span class="tar"><b style="font-weight:550">${x.n}</b>${i?` <span class="faint small">${f[i-1].n?Math.round(100*x.n/f[i-1].n):0}%</span>`:''}</span></div>`).join('')}</div>`;
}
function dayBuckets(cid,n){
 const out=[];for(let i=n-1;i>=0;i--){const t=S.now-i*D;const k=dayKey(t);out.push({l:DAYS[new Date(t).getUTCDay()],a:S.msgs.filter(m=>m.dir==='out'&&m.status==='sent'&&!m.reply&&dayKey(m.t)===k&&(cid?m.cid===cid:1)).length,b:S.msgs.filter(m=>m.dir==='in'&&dayKey(m.t)===k&&(cid?m.cid===cid:1)).length,ch:['email','linkedin','sms','voice'].map(c=>S.msgs.filter(m=>m.dir==='out'&&m.status==='sent'&&!m.reply&&m.ch===c&&dayKey(m.t)===k&&(cid?m.cid===cid:1)).length)})}
 return out;
}
/* ---------- diff ---------- */
function lcs(a,b){const n=a.length,m=b.length;const d=Array.from({length:n+1},()=>new Uint16Array(m+1));for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)d[i][j]=a[i]===b[j]?d[i+1][j+1]+1:Math.max(d[i+1][j],d[i][j+1]);return d}
function diffSeq(a,b){const d=lcs(a,b);let i=0,j=0;const A=[],B=[];while(i<a.length&&j<b.length){if(a[i]===b[j]){A.push([a[i],0]);B.push([b[j],0]);i++;j++}else if(d[i+1][j]>=d[i][j+1]){A.push([a[i],1]);i++}else{B.push([b[j],1]);j++}}
 while(i<a.length)A.push([a[i++],1]);while(j<b.length)B.push([b[j++],1]);return{A,B}}
function diffWordsHtml(a,b){const r=diffSeq(a.split(/(\s+)/),b.split(/(\s+)/));const f=(arr,c)=>arr.map(([t,x])=>x&&t.trim()?`<span class="${c}">${esc(t)}</span>`:esc(t)).join('');return{a:f(r.A,'del'),b:f(r.B,'add')}}
function diffLinesHtml(a,b){const r=diffSeq(a,b);const f=(arr,c)=>arr.map(([t,x])=>`<span class="dl ${x?c:''}">${esc(t)||'&nbsp;'}</span>`).join('');return{a:f(r.A,'del'),b:f(r.B,'add')}}
/* ---------- overlays ---------- */
function openModal(html,size){closeModal();const o=document.createElement('div');o.className='scrim';o.id='modal';o.innerHTML=`<div class="modal ${size||''}" role="dialog" aria-modal="true">${html}</div>`;o.addEventListener('mousedown',e=>{if(e.target===o)closeModal()});$('#overlay').appendChild(o);const f=o.querySelector('input,textarea,select');if(f&&!f.matches('[type=hidden]')&&size!=='keep')setTimeout(()=>f.focus(),30)}
function closeModal(){const m=$('#modal');if(m)m.remove()}
function openDrawer(html){closeDrawer();const o=document.createElement('div');o.className='drawerwrap';o.id='drawer';o.innerHTML=`<aside class="drawer" role="dialog" aria-label="Decision trace">${html}</aside>`;o.addEventListener('mousedown',e=>{if(e.target===o)closeDrawer()});$('#overlay').appendChild(o)}
function closeDrawer(){const m=$('#drawer');if(m)m.remove()}
function confirmBox(title,body,label,fn,danger){
 openModal(`<h2>${title}</h2><div class="muted" style="margin-top:8px">${body}</div><div class="mf"><button class="btn" data-a="closeModal">Cancel</button><button class="btn ${danger?'dan':'pri'}" id="cfm">${label}</button></div>`);
 $('#cfm').onclick=()=>{closeModal();fn()};
}
let toastT=null;
function toast(msg,o){o=o||{};const w=$('#toasts');w.innerHTML=`<div class="toast ${o.bad?'bad':''}" role="status"><span>${msg}</span>${o.undo?'<button id="tundo">Undo</button>':''}</div>`;if(o.undo)$('#tundo').onclick=()=>{w.innerHTML='';o.undo()};clearTimeout(toastT);toastT=setTimeout(()=>{w.innerHTML=''},o.ms||5200)}
/* ---------- routing ---------- */
function go(p){UI.path=p;UI.keep=false;try{if(location.hash!=='#'+p)location.hash='#'+p}catch(e){}closeDrawer();paint()}
function repaint(){UI.keep=true;paint()}
window.addEventListener('hashchange',()=>{const p=(location.hash||'#/overview').slice(1);if(p!==UI.path){UI.path=p;UI.keep=false;paint()}});
/* ---------- shell ---------- */
const NAVI=[['overview','Command Center','grid'],['approvals','Approvals','inbox'],['campaigns','Campaigns','layers'],['prospects','Prospects','users'],['conversations','Conversations','msg'],['activity','Agent Activity','zap'],['analytics','Analytics','chart']];
function shell(body,seg){
 const me=S.user,isRep=me.role==='Rep',n=needsCount();
 const cur=UI.path.split('/')[1]||'overview';
 const nav=NAVI.map(x=>`<a data-go="/${x[0]}" class="${cur===x[0]?'on':''}">${ic(x[2],18)}${x[1]}${x[0]==='approvals'?`<span class="badge ${n?'hot':''}" id="nb">${n}</span>`:''}</a>`).join('');
 const camps=S.camps.filter(c=>c.status!=='archived').map(c=>`<a data-go="/campaigns/${c.id}/overview" class="${UI.path.startsWith('/campaigns/'+c.id)?'on':''}"><i class="dot ${c.status==='live'?'live':c.status==='paused'?'pause':'draft'}"></i><span class="trunc">${esc(c.name)}</span></a>`).join('');
 const ws=[['prompts','Prompts and Harness','file'],['knowledge','Knowledge Base','book']].concat(isRep?[]:[['settings/integrations','Settings','gear']]).map(x=>`<a data-go="/${x[0]}" class="${cur===x[0].split('/')[0]?'on':''}">${ic(x[2],18)}${x[1]}</a>`).join('');
 const reps=S.users.filter(u=>u.role==='Rep').map(u=>`<div class="member" data-go="/prospects?rep=${u.id}">${av(u.name,'',u.active)}<div><b>${esc(u.name)}</b><small>${u.label}, ${esc(u.title)}${u.active?'':' (offboarded)'}</small></div></div>`).join('');
 const kill=S.kill?`<div class="killbar" role="alert">${ic('stop',18)}<span>KILL SWITCH ACTIVE since ${fT(S.kill.at)} by ${esc(S.kill.by)}. All outreach halted.</span>${me.role!=='Rep'?'<button class="btn sm right" data-a="killOff">Resume platform</button>':''}</div>`:'';
 const killBtn=me.role==='Rep'?'':(S.kill?`<button class="btn sm" data-a="killOff">${ic('play',14)}Resume platform</button>`:`<button class="btn dan sm" data-a="killAsk">${ic('power',14)}Stop all</button>`);
 return`<div class="app"><aside class="side" id="side"><div class="brand"><i>${ic('route',16).replace('currentColor','#f6f7ee')}</i>Cadence</div>
 <nav class="nav">${nav}</nav>
 <h6>Campaigns<button data-go="/campaigns/new" aria-label="New campaign">${ic('plus',15)}</button></h6><nav class="nav">${camps}</nav>
 <h6>Workspace</h6><nav class="nav">${ws}</nav>
 <h6>Reps<button data-go="/settings/reps" aria-label="Manage reps">${ic('plus',15)}</button></h6>${reps}
 <div class="me">${av(me.name,'',true)}<div><b>${esc(me.name)}</b><small>${me.role}</small></div><button data-a="pwOpen" aria-label="Change password">${ic('lock',18)}</button><button data-a="logout" aria-label="Sign out">${ic('logout',18)}</button></div></aside>
 <main class="main" id="main">${kill}${NET.err?`<div class="banner bad" role="alert" style="border-radius:0">${ic('alert',16)}<span>Cannot reach the server. Retrying in 5 seconds. Last update ${NET.last?fT(S.now-(Date.now()-NET.last)):'not yet'}.</span></div>`:''}<div class="topbar"><button class="iconbtn side-toggle" data-a="sideToggle" aria-label="Menu">${ic('menu',18)}</button>
 <div class="search">${ic('search',16)}<input id="gs" placeholder="Search prospects, companies, campaigns" autocomplete="off" value="${esc(UI.q)}"><div id="sres"></div></div>
 <select class="sel sm" style="width:auto;max-width:220px" data-i="campSw" aria-label="Switch campaign"><option value="">Switch campaign</option>${S.camps.filter(c=>c.status!=='archived').map(c=>`<option value="${c.id}">${c.id} ${esc(c.name)}</option>`).join('')}</select>
 <span class="right"></span><span class="clock" title="The demo clock moves when you use Advance 24 hours in Settings">${ic('clock',14)}<span>Demo clock <b id="clk">${fDT(S.now)}</b></span></span>
 <button class="iconbtn" data-go="/approvals" aria-label="Approvals">${ic('bell',18)}<span class="n" id="bn" ${n?'':'hidden'}>${n}</span></button>${killBtn}</div>
 <div class="view" id="view">${body}</div></main></div>`;
}
const GATES={};
function gateFor(x){
 if(x.status!=='open')return null;
 const c=GATES[x.id];
 if(!c||(!c.busy&&Date.now()-c.at>20000)){
  GATES[x.id]={at:c?c.at:0,gate:c?c.gate:null,busy:true};
  api.get('/approvals/'+x.id+'/gate').then(r=>{GATES[x.id]={at:Date.now(),gate:r.gate};paint()}).catch(()=>{GATES[x.id]={at:Date.now(),gate:null}});
 }
 return GATES[x.id].gate;
}
function paint(){
 const root=$('#root');
 if(!S){root.innerHTML=loginPage();return}
 const m0=$('#main');const st=UI.keep&&m0?m0.scrollTop:0;
 const boards=$$('.board').map(b=>b.scrollLeft);
 const parts=UI.path.split('?')[0].split('/').filter(Boolean);
 let html;
 try{html=pageFor(parts)}catch(err){console.error(err);html=`<div class="pad"><div class="banner bad">${ic('alert',18)}This screen hit an error: ${esc(err.message)}. <button class="btn sm" data-go="/overview">Back to Command Center</button></div></div>`}
 root.innerHTML=shell(html);
 const m=$('#main');if(m)m.scrollTop=st;$$('.board').forEach((b,i)=>{if(boards[i])b.scrollLeft=boards[i]});
 if(!UI.keep)document.title='Cadence, '+(({overview:'Command Center',approvals:'Approvals',campaigns:'Campaigns',prospects:'Prospects',conversations:'Conversations',activity:'Agent Activity',analytics:'Analytics',prompts:'Prompts and Harness',knowledge:'Knowledge Base',settings:'Settings'})[parts[0]]||'Cadence');
 if(typeof afterPaint==='function')afterPaint(parts);
}
function pageFor(p){
 const r=p[0]||'overview';
 const rep=S.user.role==='Rep';
 if(r==='overview')return pgOverview();
 if(r==='approvals')return pgApprovals();
 if(r==='campaigns'){if(p[1]==='new')return rep?deny('Only managers and admins create campaigns.'):pgCreate();if(p[1])return pgCampaign(p[1],p[2]||'overview');return pgCampaigns()}
 if(r==='prospects'){if(p[1])return pgProspect(p[1]);return pgProspects()}
 if(r==='conversations')return pgConversations(p[1]);
 if(r==='activity')return pgActivity(null);
 if(r==='analytics')return pgAnalytics();
 if(r==='prompts')return pgPrompts(null);
 if(r==='knowledge')return pgKnowledge(null);
 if(r==='settings')return rep?deny('Settings are for admins and managers.'):pgSettings(p[1]||'integrations');
 return`<div class="pad">${empty('This page does not exist','Use the left menu to get back to work.',`<br><button class="btn pri" data-go="/overview">Command Center</button>`)}</div>`;
}
function deny(t){return`<div class="pad">${empty('Not available for your role',t,`<br><button class="btn pri" data-go="/overview">Command Center</button>`)}</div>`}
function band(o){
 return`<div class="band ${o.slim?'slim':''}"><div class="crumbs">${(o.crumbs||[]).map((c,i,a)=>c[1]?`<a data-go="${c[1]}">${c[0]}</a>${i<a.length-1?ic('right',12):''}`:`<span>${c[0]}</span>`).join('')}</div>
 <div class="pagehead"><div style="min-width:0"><div class="h1">${o.title}</div>${o.sub?`<div class="sub">${o.sub}</div>`:''}</div><div class="acts">${o.acts||''}</div></div>${o.extra||''}</div>`;
}
/* ---------- login ---------- */
function loginPage(){
 const pts=[['route','One autonomous SDR across email, LinkedIn, SMS and voice'],['shield','A policy gate checks every message before it leaves'],['users','Managers set the rules and step in where a person matters']];
 return`<div class="login"><div class="l"><div class="brand" style="padding-left:0"><i>${ic('route',16).replace('currentColor','#f6f7ee')}</i>Cadence</div>
 <div class="h1" style="margin-top:8px">Sign in to your sales operation</div><p class="sub">Cadence works your outbound as one autonomous SDR. You set the rules, it runs the pipeline, and you step in where a human matters.</p>
 <div class="col gap12" style="margin-top:26px"><div class="field"><label for="lem">Email</label><input class="inp" id="lem" value="" placeholder="you@company.com" autocomplete="username"></div>
 <div class="field"><label for="lpw">Password</label><input class="inp" id="lpw" type="password" autocomplete="current-password"><div class="err" id="lerr" hidden>Email or password is wrong.</div></div>
 <button class="btn pri" id="lgo" data-a="login" style="justify-content:center">Sign in</button></div></div>
 <div class="r">${pts.map(x=>`<div class="row gap12" style="align-items:flex-start"><span class="ico">${ic(x[0],18)}</span><div class="h3" style="font-weight:500">${x[1]}</div></div>`).join('')}</div></div>`;
}
const chipOf=cid=>`<span class="chip ${COLORS[cid]||'cx'}"><i class="dot ${COLORS[cid]||'cx'}"></i>${cid}</span>`;

/* ---------- helpers for pages ---------- */
function qs(){const i=UI.path.indexOf('?');return new URLSearchParams(i<0?'':UI.path.slice(i+1))}
function findFact(id){for(const p of Object.values(S.people)){const f=p.facts.concat(p.rich).find(x=>x.id===id);if(f)return{f,p}}return null}
const ICO={discover:'search',research:'search',qualify:'target',plan:'route',draft:'edit',send:'send',reply:'msg',gate:'shield',conflict:'shield',approval:'check',meeting:'calendar',stop:'stop',pause:'pause',resume:'play',kill:'power',replan:'branch',handoff:'handoff',call:'phone',agent:'gear',channel:'gear'};
function feedItem(a,showCamp){
 const p=a.pid&&P(a.pid);const m=a.msgId&&S.msgs.find(x=>x.id===a.msgId);
 const go=a.runId?`data-a="trace" data-id="${a.runId}"`:(a.pid?`data-go="/prospects/${a.pid}"`:(a.cid?`data-go="/campaigns/${a.cid}/overview"`:''));
 const nw=S.newActs.includes(a.id);
 return`<div class="fi ${nw?'new':''}" ${go}><span class="ico">${ic(m&&a.kind==='send'?(CH[m.ch]||{}).i||'send':ICO[a.kind]||'spark',15)}</span><div class="ftx">${a.cid&&showCamp!==false?campChip(a.cid)+' ':''}${esc(a.text)}${a.mode?' '+modeTag(a.mode):''}${a.agent?` <span class="faint small">${esc(a.agent)}</span>`:''}</div><time>${rel(a.t)}</time></div>`;
}
function feedList(n,cid){const l=S.acts.filter(a=>!a.quiet&&(!cid||a.cid===cid)).slice(0,n);return l.length?`<div class="feed">${l.map(a=>feedItem(a)).join('')}</div>`:empty('No events yet','Events appear here as agents work.')}
function jobsToday(){return S.jobs.filter(j=>j.status==='done'&&!j.replay&&dayKey(j.end||j.at)===dayKey(S.now)).length}
/* ---------- Command Center ---------- */
function pgOverview(){
 const me=S.user,live=S.camps.filter(c=>c.status==='live'),n=needsYou();
 const today=dayKey(S.now);const touches=S.msgs.filter(m=>m.dir==='out'&&m.status==='sent'&&!m.reply&&dayKey(m.t)===today).length;
 const replies=S.msgs.filter(m=>m.dir==='in'&&dayKey(m.t)===today).length;
 const meet=S.meetings.filter(m=>m.at>=S.now&&m.at<S.now+7*D).length;
 const flight=S.enr.filter(e=>['researched','qualified','awaiting_approval','awaiting_voice','contacted','replied_pos','replied_obj','escalated','deferred','new'].includes(e.st)&&C(e.cid).status!=='draft').length;
 const inflightJobs=S.jobs.filter(j=>j.status==='queued'||j.status==='running').length;
 const spend=S.jobs.filter(j=>j.status==='done'&&!j.replay&&dayKey(j.end||j.at)===today).reduce((a,j)=>a+(j.cost||0),0);
 const all=cstats(null);const days=dayBuckets(null,7);
 const tot=days.reduce((a,d)=>a+d.a,0),rp=days.reduce((a,d)=>a+d.b,0);
 const hour=Math.floor((S.now%D)/H);const greet=hour<12?'Good morning':hour<17?'Good afternoon':'Good evening';
 const done=jobsToday();
 const tile=(v,l,go)=>`<button class="tile" data-go="${go}"><b>${v}</b><span>${l}</span></button>`;
 const cards=S.camps.filter(c=>c.status!=='archived').map(c=>{
  const s=cstats(c.id),f=funnel(c.id),mx=Math.max(1,f[0].n);
  const cls=c.status==='paused'?'paused':c.status==='draft'?'draftc':'';
  const bar=`<div class="mini" title="Discovered ${f[0].n}, Qualified ${f[2].n}, Contacted ${f[3].n}, Engaged ${f[4].n}, Meeting ${f[5].n}">${[f[2],f[3],f[4],f[5]].map(x=>`<i style="width:${100*x.n/mx}%"></i>`).join('')}</div>`;
  const act=c.status==='live'?`<button class="btn sm" data-a="pause" data-id="${c.id}">${ic('pause',14)}Pause</button>`:c.status==='paused'?`<button class="btn sm warn" data-a="resume" data-id="${c.id}">${ic('play',14)}Resume</button>`:c.status==='draft'?`<button class="btn sm" data-go="/campaigns/${c.id}/config">Finish setup</button>`:'';
  return`<div class="kcard ccard ${cls}" data-go="/campaigns/${c.id}/overview" role="link" tabindex="0"><div class="t">${campChip(c.id)}<span class="trunc">${esc(c.name)}</span><span class="more">${statusPill(c)}</span></div>
  <p>${c.status==='paused'?`Paused by ${esc(c.pausedBy||'a manager')} ${rel(c.pausedAt||S.now)}. ${heldCount(c.id)} jobs held.`:esc(c.icp)}</p>${bar}
  <div class="foot" style="margin-top:12px"><span class="fchip">${ic('users',13)}${s.prospects}</span><span class="fchip">${ic('msg',13)}${s.replies}</span><span class="fchip">${ic('calendar',13)}${s.meetings}</span><span class="right"></span>${act}</div>
  <div class="detail"><div>Objective: ${esc(c.objective)}</div><div style="margin-top:4px">Channels: ${Object.keys(c.channels).filter(k=>c.channels[k]).map(k=>CH[k].n).join(', ')||'none'}. Cap ${c.cap} a day. Reps: ${c.reps.map(r=>first(U(r).name)).join(', ')}.</div></div></div>`}).join('');
 const nlist=[...n.appr.slice(0,5).map(a=>{const e=E(a.eid),p=P(e.pid);const why={borderline:`Score ${e.score} sits near the ${C(e.cid).thr} threshold`,first_touch:`First touch for ${C(e.cid).name} needs sign-off`,voice:'Voice call needs approval',reply:'Reply needs approval'}[a.kind];return`<div class="fi" data-go="/approvals"><span class="avatar sm a${hash(p.name)%6}">${initials(p.name)}</span><div class="ftx"><b style="font-weight:550">${esc(p.name)}</b> ${campChip(e.cid)}<div class="muted small">${why}</div></div><button class="btn xs">Review</button></div>`}),
  ...n.esc.map(x=>{const p=P(E(x.eid).pid);return`<div class="fi" data-go="/approvals"><span class="avatar sm a${hash(p.name)%6}">${initials(p.name)}</span><div class="ftx"><b style="font-weight:550">${esc(p.name)}</b> ${campChip(x.cid)}<div class="muted small">Escalation: ${ESC[x.reason]}</div></div><button class="btn xs">Open</button></div>`}),
  ...n.conf.map(x=>{const p=P(x.pid);return`<div class="fi" data-go="/approvals"><span class="avatar sm a${hash(p.name)%6}">${initials(p.name)}</span><div class="ftx"><b style="font-weight:550">${esc(p.name)}</b> ${x.cids.map(campChip).join(' ')}<div class="muted small">Two campaigns want this prospect</div></div><button class="btn xs">Decide</button></div>`})];
 const al=alerts();
 return`<div class="band"><div class="pagehead"><div><div class="h1">${greet}, ${esc(first(me.name))}</div><div class="sub"><b>${needsCount()}</b> ${needsCount()===1?'item needs':'items need'} your decision. ${live.length} of ${S.camps.filter(c=>c.status!=='draft').length} campaigns are working.</div></div>
 <div class="acts"><button class="pill live" data-go="/activity" style="border:0;cursor:pointer;height:32px">${ic('spark',13)}Agents finished ${done} jobs today</button>${me.role!=='Rep'?`<button class="btn pri" data-go="/campaigns/new">${ic('plus',16)}New campaign</button>`:''}</div></div>
 <div class="row wrap gap24" style="margin-top:26px;align-items:flex-end;justify-content:space-between">
  <div style="width:min(340px,100%)"><div class="h3" style="font-weight:450">Touches and replies, last 7 days</div>${barsHatched(days,340,132)}<div class="row gap12 small muted"><span class="row gap4"><i style="width:10px;height:10px;background:#1f201d;border-radius:3px;display:inline-block"></i>Touches sent (${tot})</span><span class="row gap4"><i style="width:10px;height:10px;border:1px solid #1f201d;border-radius:3px;display:inline-block;background:repeating-linear-gradient(45deg,#1f201d 0 2px,#f6f7ee 2px 5px)"></i>Replies (${rp})</span></div></div>
  <div>${gauge(all.replyRate,'Reply rate')}</div>
  <div class="kpi small"><div class="stat"><b>${inflightJobs}</b><span>Jobs in flight</span><a data-go="/activity">Open Agent Activity ${ic('arrow',13)}</a></div><div class="stat"><b>${money(spend)}</b><span>Model spend today</span><a data-go="/analytics">Open Analytics ${ic('arrow',13)}</a></div></div></div></div>
 <div class="pad"><div class="kpirow" id="tiles">${tile(live.length,'Live campaigns','/campaigns')}${tile(flight,'Prospects in flight','/prospects')}${tile(touches,'Touches today','/activity')}${tile(replies,'Replies today','/conversations')}${tile(meet,'Meetings this week','/conversations')}${tile(needsCount(),'Need you: approvals, escalations, conflicts','/approvals')}</div>
 <div class="row" style="margin:28px 0 14px"><div class="h2">Campaigns</div><span class="right"></span><button class="btn sm" data-go="/campaigns">All campaigns</button></div>
 <div class="grid g4" id="ccards">${cards}</div>
 <div class="split wide" style="margin-top:30px"><div class="card"><div class="cardhead"><div class="h3">Live feed</div><select class="sel sm" style="width:auto" data-i="feedCamp"><option value="">All campaigns</option>${S.camps.map(c=>`<option value="${c.id}" ${UI.fil.feed===c.id?'selected':''}>${c.id} ${esc(c.name)}</option>`).join('')}</select></div><div id="feedbox">${feedList(20,UI.fil.feed)}</div></div>
 <div class="col gap16"><div class="card"><div class="cardhead"><div class="h3">Needs you</div><button class="btn xs" data-go="/approvals">Open inbox</button></div>${nlist.length?`<div class="feed">${nlist.join('')}</div>`:empty('Nothing needs you','The agents are working.')}</div>
 <div class="card"><div class="cardhead"><div class="h3">Alerts</div></div>${al.length?`<div class="col">${al.map(a=>`<div class="banner ${a.t==='bad'?'bad':'paused'}" style="font-weight:450;cursor:pointer;align-items:flex-start" data-go="${a.go.slice(1)}">${ic(a.ic,16)}<span>${esc(a.x)}</span></div>`).join('')}</div>`:'<div class="muted">No alerts. Every agent, channel and integration is healthy.</div>'}</div></div></div></div>`;
}
/* ---------- trace drawer ---------- */
function traceHtml(j){
 const e=j.eid&&E(j.eid),p=e&&P(e.pid),c=C(j.cid),tr=j.tr||{};const role=roleOf(j);
 const st=jobState(j);
 const msg=j.msgId&&S.msgs.find(m=>m.id===j.msgId);
 const chunks=(tr.chunks||[]).filter(k=>S.kb.chunks[k]).map(k=>{const ch=S.kb.chunks[k],d=S.kb.docs.find(x=>x.id===ch.doc);return`<details class="sec" style="margin:0 0 8px"><summary style="padding:10px 14px;font-size:13.5px"><span class="mono">${k}</span><span class="muted" style="font-weight:450">${esc(d?d.name:'')}</span>${ic('down',14).replace('class="ic"','class="ic chev"')}</summary><div class="body muted small" style="padding-top:0">${esc(ch.text)}</div></details>`}).join('');
 const vers=S.prompts.filter(x=>x.cid===j.cid&&x.role===role&&x.v!==j.pv);
 const canReplay=['Writer','Qualifier','Sequencer'].includes(j.agent)&&j.status==='done'&&e&&!j.replay&&vers.length;
 return`<div class="row"><span class="h2">${esc(j.agent)}</span><span class="mono faint">${j.id}</span>${j.replay?'<span class="tag replay">REPLAY</span>':''}<span class="right"></span><button class="btn ghost sm" data-a="closeDrawer" aria-label="Close">${ic('x',16)}</button></div>
 <div class="row wrap" style="margin:10px 0 18px">${campChip(j.cid,true)}${p?`<a class="chip line" data-go="/prospects/${p.id}" style="cursor:pointer">${ic('user',12)}${esc(p.name)}</a>`:''}<span class="pill ${j.status==='done'?'done':j.status==='failed'?'bad':st==='held'?'paused':'info'}">${j.status==='queued'?st:j.status}${st==='held'?': '+heldReason(j):''}</span>${msg?modeTag(msg.mode):''}</div>
 ${j.status==='failed'?`<div class="banner bad" style="margin-bottom:14px">${ic('alert',16)}<span>${esc(j.err||'Failed')}</span><button class="btn sm right" data-a="retry" data-id="${j.id}">Retry</button></div>`:''}
 ${j.status==='done'||j.status==='failed'?`<dl class="kv"><dt>Model</dt><dd>${esc(j.model||AG[j.agent].model)}</dd><dt>Prompt version</dt><dd>${role} v${j.pv} <span class="faint">(campaign version ${j.cv})</span></dd><dt>Latency</dt><dd>${j.dur}s</dd><dt>Cost</dt><dd>${money(j.cost||0)} <span class="faint small">${j.tin||0} tokens in, ${j.tout||0} out</span></dd><dt>Run at</dt><dd>${fDT(j.end||j.at)}${j.seed?' '+demoTag:''}</dd></dl>`:`<div class="muted">This job has not run yet. It runs when the campaign is Live and the ${esc(j.agent)} agent is on.</div>`}
 ${tr.input?`<hr class="s"><div class="lbl">Input summary</div><div class="muted" style="margin-top:6px">${esc(tr.input)}</div>`:''}
 ${chunks?`<hr class="s"><div class="lbl" style="margin-bottom:8px">Retrieved knowledge</div>${chunks}`:''}
 ${tr.output?`<hr class="s"><div class="lbl" style="margin-bottom:8px">Output</div><div class="pre" id="trout">${esc(tr.output)}</div>`:''}
 ${tr.segs&&tr.claims&&tr.claims.length?`<hr class="s"><div class="lbl" style="margin-bottom:6px">Grounding check</div><div class="muted small">${tr.grounded?`${tr.grounded.total-tr.grounded.bad} of ${tr.grounded.total} claims trace to a source.`:''}</div>${evidenceBlock(tr.segs,false)}`:''}
 ${tr.gate?`<hr class="s"><div class="row"><div class="lbl">Gate decision</div><span class="pill ${tr.gate.dec==='allow'?'live':tr.gate.dec==='needs_approval'?'warn':'paused'}">${tr.gate.dec}${tr.gate.reason?': '+tr.gate.reason:''}</span></div><div style="margin-top:6px">${gateView(tr.gate)}</div>`:''}
 ${canReplay?`<hr class="s"><div class="lbl">Replay this input with another prompt version</div><div class="muted small" style="margin:4px 0 10px">Dry run only. Nothing is sent and the run is tagged replay.</div><div class="row"><select class="sel sm" id="rpv" style="width:auto">${vers.map(v=>`<option value="${v.v}">${role} v${v.v}${v.status==='active'?' (active)':''}</option>`).join('')}</select><button class="btn sm" data-a="replay" data-id="${j.id}">${ic('branch',14)}Replay</button></div><div id="rpout" style="margin-top:14px"></div>`:''}`;
}
function evidenceBlock(segs,showNote){
 const srcs=[];const html=segs.map(s=>{
  if(!s.src)return esc(s.t).replace(/\n/g,'<br>');
  let i=srcs.indexOf(s.src);if(i<0){srcs.push(s.src);i=srcs.length-1}
  return`${esc(s.t)}<sup class="cite ${s.src==='?'?'bad':''}" data-a="${s.src[0]==='F'?'openFact':'openChunk'}" data-id="${s.src}" title="Source ${i+1}">${s.src==='?'?'!':i+1}</sup>`}).join('');
 const bad=segs.filter(s=>s.src==='?');
 const list=srcs.map((s,i)=>{
  if(s==='?')return`<div class="row" style="align-items:flex-start"><span class="chip">!</span><div class="small" style="color:var(--kill)">No evidence found for: "${esc(segs.find(x=>x.src==='?').t)}"</div></div>`;
  if(s[0]==='K'){const ch=S.kb.chunks[s];const d=ch&&S.kb.docs.find(x=>x.id===ch.doc);return`<div class="row" style="align-items:flex-start"><span class="chip">${i+1}</span><div class="small"><b style="font-weight:550">${esc(d?d.name:s)}</b> <span class="mono faint">${s}</span><div class="muted">${esc(ch?ch.text:'')}</div></div></div>`}
  const f=findFact(s);return`<div class="row" style="align-items:flex-start"><span class="chip">${i+1}</span><div class="small"><b style="font-weight:550">${f?esc(f.p.company):''}</b> <span class="conf ${f?f.f.conf:''}">${f?f.f.conf:''}</span> <a class="why" data-a="openFact" data-id="${s}">${f?esc(f.f.url):''}</a><div class="muted">${f?esc(f.f.text):''}</div></div></div>`}).join('');
 return`<div class="msg" style="background:#fff">${html}</div>${bad.length?`<div class="banner bad" style="margin-top:10px;font-weight:450;align-items:flex-start">${ic('shield',16)}<span><b>Verifier blocked this draft.</b> A claim states "${esc(bad[0].t)}" with no evidence linked to it. The Writer must remove it or find a source before anything sends.</span></div>`:''}${srcs.length?`<div class="lbl" style="margin:14px 0 6px">Sources</div><div class="col gap12">${list}</div>`:''}${showNote!==false?`<div class="muted small" style="margin-top:12px">A sentence with no marker is ours, not the evidence's: the greeting, the pitch and the ask. Only claims traced to a retrieved fact or knowledge chunk carry a marker.</div>`:''}`;
}
ACT.openFact=t=>{const r=findFact(t.dataset.id);if(!r)return;const{f,p}=r;
 const body={careers:'Open roles<br>Senior Platform Engineer<br>Staff Engineer, Internal Tools<br>Platform Reliability Engineer',docs:'API reference. Authentication, rate limits, webhooks and SDKs for '+esc(p.company)+' customers.',about:esc(p.company)+' at a glance. Team size, funding and headquarters in '+esc(p.city)+'.',blog:'Engineering blog. How we run our internal tools today and what slows the team down.',rbi:'Regulated entity register. Entity category, registered office in '+esc(p.city)+' and licence status.',news:'Press release. The company describes the programme and its planned first phase.',annual:'Annual report, risk section. Obligations on data localisation and vendor oversight.',product:'Product page. Live voice features, supported channels and customer logos.',linkedin:'Public post by '+esc(p.name)+'. Notes on what the team shipped and learned this week.'}[f.src]||'Page excerpt.';
 openModal(`<div class="row"><h2>Source page</h2>${demoTag}<span class="right"></span><button class="btn ghost sm" data-a="closeModal">${ic('x',16)}</button></div><div class="mono faint" style="margin:8px 0 14px">${esc(f.url)}</div><div class="card flat"><div class="h3">${esc(p.company)}</div><div class="muted" style="margin:6px 0 12px">${body}</div><div style="background:#fff;border-radius:12px;padding:12px 14px;border:1px solid var(--line)"><span class="conf ${f.conf}">${f.conf} confidence</span><div style="margin-top:8px">${esc(f.text)}</div></div></div><p class="muted small" style="margin-top:12px">Fictional companies have no web presence, so the Researcher saves facts from these hosted pages. Each fact keeps its source URL and confidence.</p>`,'lg');
};
ACT.openChunk=t=>{const ch=S.kb.chunks[t.dataset.id];if(!ch)return;const d=S.kb.docs.find(x=>x.id===ch.doc);openModal(`<div class="row"><h2>${esc(d?d.name:ch.id)}</h2><span class="mono faint">${ch.id}</span><span class="right"></span><button class="btn ghost sm" data-a="closeModal">${ic('x',16)}</button></div><div class="card flat" style="margin-top:14px">${esc(ch.text)}</div><p class="muted small" style="margin-top:12px">${d&&d.scope==='global'?'Global knowledge, used by every campaign.':'Knowledge for '+(d?d.scope:'')+' only.'}</p>`)};
ACT.trace=t=>{const j=S.jobs.find(x=>x.id===t.dataset.id);if(j)openDrawer(traceHtml(j))};
ACT.closeDrawer=()=>closeDrawer();ACT.closeModal=()=>closeModal();


/* ---------- Approvals ---------- */
function apprItems(tab){
 const n=needsYou();
 if(tab==='escalations')return n.esc;if(tab==='conflicts')return n.conf;return n.appr;
}
const KLAB={borderline:'Borderline ICP call',first_touch:'First-touch draft',voice:'Voice call',reply:'Reply draft',prompt_change:'Prompt change'};
function pgApprovals(){
 const tab=UI.tab.appr||'approvals';const n=needsYou();
 const items=apprItems(tab);
 if(!items.find(x=>x.id===UI.sel.appr))UI.sel.appr=items[0]&&items[0].id;
 const sel=items.find(x=>x.id===UI.sel.appr);
 const list=items.map(x=>{
  if(tab==='conflicts'){const p=P(x.pid);return`<div class="item ${x.id===UI.sel.appr?'on':''}" data-a="selAppr" data-id="${x.id}">${av(p.name)}<div class="grow"><b>${esc(p.name)}</b><div class="small muted">${x.cids.join(' vs ')}, ${esc(p.company)}</div></div><span class="faint small">${rel(x.t)}</span></div>`}
  const e=E(x.eid),p=P(e.pid);
  return`<div class="item ${x.id===UI.sel.appr?'on':''}" data-a="selAppr" data-id="${x.id}">${av(p.name)}<div class="grow"><b>${esc(p.name)}</b> ${campChip(x.cid)}<div class="small muted trunc">${tab==='escalations'?ESC[x.reason]:KLAB[x.kind]}, ${esc(p.company)}</div></div><span class="faint small">${rel(x.t)}</span></div>`}).join('');
 const resolved=tab==='conflicts'?S.conflicts.filter(c=>c.status!=='open').slice(-4):[];
 return`${band({slim:true,crumbs:[['Command Center','/overview'],['Approvals']],title:'Approvals inbox',sub:'The single queue for everything that needs a human.'})}
 ${tabs([{k:'approvals',l:'Approvals',n:n.appr.length},{k:'escalations',l:'Escalations',n:n.esc.length},{k:'conflicts',l:'Conflicts',n:n.conf.length}],tab,'apprTab')}
 <div class="pad"><div class="split wide" style="grid-template-columns:340px minmax(0,1fr)">
 <div class="card tight" style="padding:8px">${items.length?list:empty('Nothing needs you','The agents are working.')}${resolved.length?`<div class="lbl" style="margin:16px 12px 6px">Recently decided</div>${resolved.map(x=>`<div class="item" style="cursor:default">${av(P(x.pid).name)}<div class="grow small"><b>${esc(P(x.pid).name)}</b><div class="muted">${esc(x.decision)}</div></div><span class="pill ${x.status==='logged'?'done':'live'}">${x.status}</span></div>`).join('')}`:''}</div>
 <div id="apprdetail">${sel?apprDetail(tab,sel):`<div class="card">${empty('Nothing selected','Pick an item on the left.')}</div>`}</div></div></div>`;
}
function apprDetail(tab,x){
 if(tab==='conflicts'){
  const p=P(x.pid),es=x.cids.map(c=>E0(p.id,c));
  return`<div class="card"><div class="row"><div class="h2">${esc(p.name)}</div>${x.cids.map(campChip).join(' ')}<span class="right"></span><button class="btn sm" data-go="/prospects/${p.id}">Open prospect</button></div><div class="muted" style="margin:6px 0 18px">${esc(p.title)} at ${esc(p.company)}. Two campaigns want this person, and only one may contact them.</div>
  <div class="grid g2">${es.map(e=>`<div class="card tight ${x.winner===e.cid?'':'flat'}"><div class="row">${campChip(e.cid,true)}<span class="right"></span>${x.winner===e.cid?'<span class="pill live">Holds the claim</span>':'<span class="pill paused">Waiting</span>'}</div><div class="row" style="margin-top:10px"><div class="stat"><b style="font-size:28px">${e.score==null?'-':e.score}</b><span>ICP score</span></div><div class="stat" style="margin-left:18px"><b style="font-size:16px;margin-top:8px">${spillText(e.st)}</b><span>State in this campaign</span></div></div></div>`).join('')}</div>
  <div class="banner mist" style="margin-top:16px;font-weight:450;align-items:flex-start">${ic('shield',16)}<span><b>Rule applied:</b> ${esc(x.rule)}. Decision: ${esc(x.decision)}. Reason code <span class="mono">${x.code}</span>.</span></div>
  <div class="row" style="margin-top:18px">${x.cids.map(c=>`<button class="btn ${c===x.winner?'':'pri'}" data-a="giveTo" data-id="${x.id}" data-c="${c}">Give to campaign ${c}</button>`).join('')}</div><p class="muted small" style="margin-top:10px">An override moves the claim, stops the other campaign's pending steps and logs who decided.</p></div>`;
 }
 const e=E(x.eid),p=P(e.pid),c=C(e.cid),rep=repFor(e);
 const head=`<div class="row"><div class="h2">${esc(p.name)}</div>${campChip(e.cid,true)}<span class="right"></span><button class="btn sm" data-go="/prospects/${p.id}">Open prospect</button></div><div class="muted" style="margin:6px 0 16px">${esc(p.title)} at ${esc(p.company)}. Rep: ${esc(rep.name)}.</div>`;
 if(tab==='escalations'){
  const inm=S.msgs.find(m=>m.id===x.msgId);
  return`<div class="card">${head}<div class="banner paused" style="font-weight:450;align-items:flex-start">${ic('handoff',16)}<span><b>${ESC[x.reason]}.</b> ${esc(x.rule)}. Agents stop here and hand the thread to ${esc(first(rep.name))}.</span></div>
  <div class="lbl" style="margin:18px 0 6px">What the prospect said</div><div class="msg in">${esc(inm?inm.body:x.summary)}</div>
  <div class="lbl" style="margin:18px 0 6px">Suggested reply</div><textarea class="txt" id="escText" rows="5">${esc(x.suggested)}</textarea><div class="muted small" style="margin-top:6px">Drafted from approved knowledge only. Agents never promise discounts.</div>
  <div class="row" style="margin-top:16px"><button class="btn pri" data-a="escSend" data-id="${x.id}">${ic('send',15)}Send reply and resolve</button><button class="btn" data-a="reassign" data-id="${x.id}" data-t="esc">Reassign</button></div></div>`;
 }
 const m=x.msgId&&S.msgs.find(z=>z.id===x.msgId);
 const g=m?gateFor(x):null;
 const li=!!m&&m.ch==='linkedin'&&chanMode('linkedin')==='live';
 if(x.kind==='borderline'){
  const cr=e.crit||[];
  return`<div class="card">${head}<div class="banner paused" style="font-weight:450;align-items:flex-start">${ic('eye',16)}<span><b>Score ${e.score==null?'-':e.score} against a threshold of ${c.thr}.</b> ${esc(e.reviewNote||'')}</span></div>${scorecard(e,cr)}
  <div class="row" style="margin-top:16px"><button class="btn pri" data-a="approve" data-id="${x.id}">${ic('check',15)}Approve as qualified</button><button class="btn" data-a="rejectAsk" data-id="${x.id}">Reject</button><button class="btn" data-a="reassign" data-id="${x.id}" data-t="appr">Reassign</button></div></div>`;
 }
 if(x.kind==='voice'){
  const rj=S.jobs.find(j=>j.id===x.runId);
  return`<div class="card">${head}<div class="banner paused" style="font-weight:450;align-items:flex-start">${ic('phone',16)}<span><b>Every voice call in ${esc(c.name)} needs approval.</b> The prospect replied warmly and has a phone on file: ${esc(p.phone)}.</span></div>
  <div class="lbl" style="margin:18px 0 6px">Call briefing</div><div class="pre">Objective: ${esc(c.objective)}\nRep on the follow-up: ${esc(rep.name)}\nFacts: ${p.facts.slice(0,3).map(f=>f.text).join(' ')}\nLast reply: "${esc((msgsOf(e).filter(m=>m.dir==='in').slice(-1)[0]||{}).body||'')}"\nScript rules: open with your name and reason, ask permission, never quote pricing.</div>
  <div class="row" style="margin-top:16px"><button class="btn pri" data-a="approve" data-id="${x.id}">${ic('phone',15)}Approve and place call</button><button class="btn" data-a="rejectAsk" data-id="${x.id}">Reject</button>${rj?`<button class="btn ghost" data-a="trace" data-id="${rj.id}">Why</button>`:''}</div></div>`;
 }
 return`<div class="card">${head}<div class="row wrap" style="margin-bottom:10px"><span class="chip line">${chIc(m.ch)}${CH[m.ch].n}</span>${modeTag(chanMode(m.ch))}<span class="pill warn">${KLAB[x.kind]}</span></div>
 ${m.subject?`<div class="lbl">Subject</div><div style="margin:4px 0 12px" id="apSubj">${esc(m.subject)}</div>`:''}
 <div class="lbl">Draft</div><div id="draftView" style="margin-top:6px">${m.segs?evidenceBlock(m.segs,true):`<div class="msg">${esc(m.body)}</div><div class="muted small" style="margin-top:6px">Edited by a person. Edited text is not re-verified.</div>`}</div>
 <div id="draftEdit" hidden><textarea class="txt" id="editText" rows="9">${esc(m.body)}</textarea></div>
 <div class="lbl" style="margin:18px 0 4px">Why it is here</div>${g?gateView(g):''}
 ${li?`<div class="banner mist" style="font-weight:450;margin-top:14px;align-items:flex-start">${ic('linkedin',16)}<span><b>You send this one.</b> LinkedIn has no API for messaging prospects, and automating an account breaks its terms. Open the profile, paste the note, send it, then confirm here.</span></div>`:''}
 <div class="row wrap" style="margin-top:16px">${li?`<button class="btn" data-a="liOpen" data-u="${esc(p.linkedin)}">${ic('linkedin',15)}Open profile</button><button class="btn" data-a="liCopy" data-id="${x.id}">${ic('copy',15)}Copy note</button>`:''}<button class="btn pri" data-a="approve" data-id="${x.id}">${ic('check',15)}${li?'I sent it on LinkedIn':'Approve'}</button><button class="btn" data-a="editAppr">${ic('edit',15)}Edit and approve</button><button class="btn" data-a="rejectAsk" data-id="${x.id}">Reject</button><button class="btn" data-a="reassign" data-id="${x.id}" data-t="appr">Reassign</button><button class="btn ghost" data-a="trace" data-id="${x.runId}">Why</button></div></div>`;
}
function spillText(st){return(STATE[st]||STATE.new).l}
function scorecard(e,cr,nolbl){
 const L={met:['Met','met'],part:['Partial','part'],unk:['Unknown','unk'],no:['Not met','nomet']};
 return`${nolbl?'':'<div class="lbl" style="margin:18px 0 6px">ICP scorecard</div>'}<div class="tblwrap"><table class="tbl"><tbody>${cr.map(x=>`<tr><td>${esc(x.label)}</td><td class="${L[x.st][1]}"><b style="font-weight:550">${L[x.st][0]}</b></td><td class="tar">${x.ev?`<a class="why" data-a="openFact" data-id="${x.ev}">Evidence</a>`:'<span class="faint small">No evidence</span>'}</td></tr>`).join('')}${e.reject?`<tr><td>Exclusion rule</td><td class="nomet"><b style="font-weight:550">Not met</b></td><td class="tar small muted">${esc(e.reject)}</td></tr>`:''}</tbody></table></div>`;
}
ACT.apprTab=t=>{UI.tab.appr=t.dataset.k;UI.sel.appr=null;repaint()};
ACT.selAppr=t=>{UI.sel.appr=t.dataset.id;repaint()};
ACT.editAppr=()=>{$('#draftView').hidden=true;$('#draftEdit').hidden=false;const b=$('[data-a=editAppr]');b.textContent='Editing: approve to send';b.classList.add('dis');$('#editText').focus()};






/* ---------- campaigns ---------- */
function campChecklist(c){
 const chunks=chunksFor(c.id,true);const docs=S.kb.docs.filter(d=>d.scope===c.id);
 const hasCase=docs.some(d=>d.type==='case study'),hasObj=docs.some(d=>d.type==='objections');
 const chOk=Object.keys(c.channels).filter(k=>c.channels[k]&&S.integ[{email:'gmail',linkedin:'linkedin',sms:'twilio',voice:'voice'}[k]].status==='ok');
 const reps=c.reps.map(U).filter(u=>u&&u.active&&u.limit>0);
 const pOk=ROLES.every(r=>S.prompts.some(p=>p.cid===c.id&&p.role===r&&p.status==='active'));
 return[
  {ok:(c.roles||[]).length>0&&(c.geoList||[]).length>0&&(c.exclusions||[]).length>0,t:'ICP has at least one role, one geography and one exclusion rule'},
  {ok:pOk,t:'Every enabled agent has an active prompt version'},
  {ok:chunks.length>=8&&hasCase&&hasObj,t:`At least 8 knowledge chunks, including one case study and one objection (${chunks.length} now)`},
  {ok:chOk.length>0,t:'At least one channel is enabled with a verified sender'},
  {ok:reps.length>0,t:'At least one rep is assigned, with limits set'},
  {ok:!!c.dryOk,t:'A dry run on 3 sample prospects passed the grounding check'}
 ];
}
function chunksFor(cid,own){const ids=new Set();S.kb.docs.forEach(d=>{if(d.scope===cid||(!own&&d.scope==='global'))d.chunks.forEach(k=>ids.add(k))});return[...ids].map(k=>S.kb.chunks[k])}
function volumeEst(c){const n=Math.min(c.cap,Object.values(c.channels).filter(Boolean).length*12);return{n,cost:n*0.056}}
function pgCampaigns(){
 const f=UI.fil.camp||'all',q=(UI.fil.campq||'').toLowerCase();const me=S.user;
 let list=S.camps.filter(c=>f==='all'?c.status!=='archived':c.status===f);
 if(q)list=list.filter(c=>(c.name+c.icp).toLowerCase().includes(q));
 if(me.role==='Rep')list=list.filter(c=>c.reps.includes(me.id));
 const rows=list.map(c=>{const s=cstats(c.id);const own=U(c.owner);const last=c.last||c.createdAt;
  const tog=c.status==='live'?`<button class="btn sm" data-a="pause" data-id="${c.id}">${ic('pause',14)}Pause</button>`:c.status==='paused'?`<button class="btn sm warn" data-a="resume" data-id="${c.id}">${ic('play',14)}Resume</button>`:'';
  return`<tr class="click ${c.status==='paused'?'paused':c.status==='draft'?'dim':''}" data-go="/campaigns/${c.id}/overview"><td><div class="row">${campChip(c.id)}<b style="font-weight:550">${esc(c.name)}</b></div></td><td class="muted" style="max-width:240px"><div class="trunc" title="${esc(c.icp)}">${esc(c.icp)}</div></td><td>${statusPill(c)}</td><td>${s.prospects}</td><td>${s.touches}</td><td>${s.replies}</td><td>${s.meetings}</td><td><div class="row">${av(own.name,'sm')}<span class="small">${esc(first(own.name))}</span></div></td><td class="muted small">${c.status==='draft'?'Not launched':rel(last)}</td><td class="tar" data-stop>${tog}<span class="menuwrap"><button class="btn ghost sm" data-a="menu" data-id="cl-${c.id}" aria-label="More">${ic('dots',16)}</button>${UI.menu==='cl-'+c.id?campMenu(c):''}</span></td></tr>`}).join('');
 return`${band({crumbs:[['Command Center','/overview'],['Campaigns']],title:'Campaigns',sub:'Compare every campaign in one table. Each one runs on its own ICP, prompts, knowledge and limits.',acts:me.role==='Rep'?'':`<button class="btn pri" data-go="/campaigns/new">${ic('plus',16)}New campaign</button>`})}
 <div class="pad"><div class="filters" style="margin-bottom:16px"><div class="seg">${['all','live','paused','draft','completed'].map(k=>`<button class="${f===k?'on':''}" data-a="campFil" data-k="${k}">${cap(k)}</button>`).join('')}</div><input class="inp" style="max-width:260px" placeholder="Search campaigns" data-i="campq" value="${esc(UI.fil.campq||'')}"></div>
 ${list.length?`<div class="tblwrap"><table class="tbl"><thead><tr><th>Campaign</th><th>ICP</th><th>Status</th><th>Prospects</th><th>Outreach</th><th>Replies</th><th>Meetings</th><th>Owner</th><th>Last activity</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`:empty(f==='all'?'No campaigns yet':'No '+cap(f)+' campaigns',f==='all'?'Create the first campaign to start.':'Change the filter to see the rest.',f==='all'?`<br><button class="btn pri" data-go="/campaigns/new">New campaign</button>`:'')}</div>`;
}
function campMenu(c){return`<div class="menu"><button data-a="dup" data-id="${c.id}">${ic('copy',15)}Duplicate as variant</button>${c.status==='live'||c.status==='paused'?`<button data-a="complete" data-id="${c.id}">${ic('check',15)}Complete</button>`:''}${c.status!=='archived'?`<button data-a="archive" data-id="${c.id}">${ic('trash',15)}Archive</button>`:''}</div>`}
ACT.menu=t=>{UI.menu=UI.menu===t.dataset.id?null:t.dataset.id;repaint()};
ACT.campFil=t=>{UI.fil.camp=t.dataset.k;repaint()};





/* ---------- campaign dashboard ---------- */
function pgCampaign(id,tab){
 const c=C(id);if(!c)return`<div class="pad">${empty('Campaign not found','It may have been archived.','<br><button class="btn pri" data-go="/campaigns">All campaigns</button>')}</div>`;
 if(S.user.role==='Rep'&&!c.reps.includes(S.user.id))return deny('This campaign belongs to other reps.');
 const s=cstats(id),ck=campChecklist(c),allOk=ck.every(x=>x.ok);
 const act=c.status==='live'?`<button class="btn pri" data-a="pause" data-id="${id}" style="height:44px">${ic('pause',16)}Pause campaign</button>`:c.status==='paused'?`<button class="btn warn" style="height:44px" data-a="resume" data-id="${id}">${ic('play',16)}Resume campaign</button>`:c.status==='draft'?`<button class="btn pri ${allOk?'':'dis'}" data-a="activate" data-id="${id}" style="height:44px">Activate</button>`:'';
 const edit=S.user.role!=='Rep'&&!['completed','archived'].includes(c.status)?`<button class="btn" data-a="campEdit" data-id="${id}" style="height:44px">${ic('edit',16)}Edit</button>`:'';
 const menu=`<span class="menuwrap"><button class="btn" data-a="menu" data-id="ch-${id}" aria-label="More" style="height:44px">${ic('dots',16)}</button>${UI.menu==='ch-'+id?campMenu(c):''}</span>`;
 const chips=Object.keys(c.channels).filter(k=>c.channels[k]).map(k=>`<span class="chip line">${chIc(k)}${CH[k].n}</span>`).join('');
 const extra=`<div class="row wrap" style="margin-top:14px">${statusPill(c)}${chips}<span class="chip line">${ic('users',12)}${c.reps.map(r=>first(U(r).name)).join(', ')}</span><span class="chip line">Owner ${esc(first(U(c.owner).name))}</span><span class="chip line">Version ${c.version}</span></div>`;
 const t=[{k:'overview',l:'Overview'},{k:'board',l:'Prospects',n:s.prospects},{k:'activity',l:'Agent Activity'},{k:'prompts',l:'Prompts'},{k:'knowledge',l:'Knowledge'},{k:'config',l:'Config'}];
 const tb=`<div class="tabs">${t.map(x=>`<a data-go="/campaigns/${id}/${x.k}" class="${tab===x.k?'on':''}">${x.l}${x.n!=null?`<span class="cnt">${x.n}</span>`:''}</a>`).join('')}</div>`;
 let body='';
 if(tab==='overview')body=campOverview(c,s,ck);else if(tab==='board')body=`<div class="pad">${prospectsView(id)}</div>`;else if(tab==='activity')body=activityView(id);else if(tab==='prompts')body=promptsView(id);else if(tab==='knowledge')body=knowledgeView(id);else if(tab==='config')body=campConfig(c,ck);
 return`${band({crumbs:[['Campaigns','/campaigns'],[esc(c.name)]],title:`${esc(c.name)}`,sub:esc(c.icp),acts:act+edit+menu,extra})}${tb}${body}`;
}
function ckList(ck){return`<div>${ck.map(x=>`<div class="check ${x.ok?'ok':'no'}"><span class="b">${x.ok?ic('check',12):''}</span><span>${esc(x.t)}</span></div>`).join('')}</div>`}
function campOverview(c,s,ck){
 const f=funnel(c.id);const days=dayBuckets(c.id,7);const held=heldCount(c.id);
 const es=enrIn(c.id);const nApp=S.approvals.filter(a=>a.cid===c.id&&a.status==='open').length,nEsc=S.escal.filter(x=>x.cid===c.id&&x.status==='open').length;
 const jobs=S.jobs.filter(j=>j.cid===c.id);const run=jobs.filter(j=>j.status==='running').length,q=jobs.filter(j=>j.status==='queued').length,done=jobs.filter(j=>j.status==='done'&&!j.replay).length,fail=jobs.filter(j=>j.status==='failed').length;
 const conflictHeld=es.filter(e=>e.st==='deferred').length;const noRep=!c.reps.some(r=>U(r).active);
 const banners=[];
 if(c.status==='paused')banners.push(`<div class="banner paused">${ic('pause',18)}<span>Paused by ${esc(c.pausedBy||'a manager')} at ${fT(c.pausedAt||S.now)}. ${held} jobs held. Resume to continue.</span><button class="btn sm warn right" data-a="resume" data-id="${c.id}">Resume</button></div>`);
 if(c.status==='draft')banners.push(`<div class="banner mist">${ic('info',18)}<span><b>Not launched.</b> Agents cannot send anything while this campaign is a Draft. Finish the checklist to activate.</span><button class="btn sm right" data-a="trySend" data-id="${c.id}">Try a send</button></div>`);
 if(noRep)banners.push(`<div class="banner bad">${ic('alert',18)}<span>No active rep. Sends defer with no_rep_available until an admin reassigns.</span><button class="btn sm right" data-go="/settings/reps">Open reps</button></div>`);
 const draft=c.status==='draft';
 const outcome=(l,v,sub)=>`<div class="stat"><b style="font-size:28px">${v}</b><span>${l}${sub?` <span class="faint small">${sub}</span>`:''}</span></div>`;
 const neg=es.filter(e=>['replied_notnow','opted_out'].includes(e.st)).length;
 const empt=s.prospects===0;
 return`<div class="pad col gap16">${banners.join('')}
 ${draft?`<div class="card"><div class="cardhead"><div class="h3">Pre-launch checklist</div><span class="row gap8"><span class="muted small">${ck.filter(x=>x.ok).length} of ${ck.length} done</span>${S.user.role!=='Rep'?`${(UI.dry||{})[c.id]?`<span class="spin" role="status" aria-label="Dry run in progress"></span><button class="btn sm dis" disabled>Running dry run</button>`:`<button class="btn sm" data-a="dryNow" data-id="${c.id}">${ic('play',14)}Run dry run</button>`}`:''}</span></div>${ckList(ck)}<div class="muted small" style="margin-top:10px">Projected volume: up to ${volumeEst(c).n} touches a day, about ${money(volumeEst(c).cost)} of model cost a day.</div></div>`:''}
 ${empt?empty('No prospects yet','Run discovery or import a CSV to fill this campaign.',`<br><div class="row" style="justify-content:center;margin-top:14px"><button class="btn pri" data-a="discover" data-id="${c.id}">Simulate discovery</button><button class="btn" data-a="importCsv" data-id="${c.id}">Import CSV</button></div>`):`
 <div class="kpirow">${[['Prospects',s.prospects],['Contacted',s.contacted],['Replies',s.replies],['Positive',s.pos],['Meetings',s.meetings],['Held now',held]].map(x=>`<div class="tile" style="cursor:default"><b>${x[1]}</b><span>${x[0]}</span></div>`).join('')}</div>
 <div class="split wide"><div class="card ${draft?'flat':''}"><div class="cardhead"><div class="h3">Funnel</div>${draft?'<span class="pill draft">Not launched</span>':''}</div>${stagebar(f)}</div>
 <div class="card"><div class="cardhead"><div class="h3">Outreach by day</div></div>${barsHatched(days,340,140)}<div class="row gap12 small muted"><span>Solid: touches sent</span><span>Hatched: replies</span></div></div></div>
 <div class="grid g3"><div class="card"><div class="cardhead"><div class="h3">Agents</div><button class="btn xs" data-go="/campaigns/${c.id}/activity">Open activity</button></div>
  <div class="row wrap gap16" style="margin-bottom:10px"><span><b>${run}</b> <span class="muted small">running</span></span><span><b>${q}</b> <span class="muted small">queued</span></span><span><b>${done}</b> <span class="muted small">completed</span></span><span><b style="color:${fail?'var(--kill)':'inherit'}">${fail}</b> <span class="muted small">failed</span></span></div>
  <div class="row wrap gap16 small" style="margin-bottom:10px"><span>Approvals <b>${nApp}</b></span><span>Escalations <b>${nEsc}</b></span></div>
  <div class="col">${AGENTS.map(a=>`<div class="row"><span class="grow">${a.k}</span>${sw(c.agents[a.k],'agentSw','data-id="'+c.id+'" data-k="'+a.k+'"',c.status==='draft'||c.status==='completed')}</div>`).join('')}</div></div>
 <div class="card"><div class="cardhead"><div class="h3">Channels</div></div><div class="col">${['email','linkedin','sms','voice'].map(k=>`<div class="row"><span class="grow row gap4">${chIc(k)}${CH[k].n} ${modeTag(chanMode(k))}</span>${sw(c.channels[k],'chanSw','data-id="'+c.id+'" data-k="'+k+'"',c.status==='completed')}</div>`).join('')}</div><div class="muted small" style="margin-top:12px">Turn a channel off and the Sequencer replans the touches onto the channels that remain.</div></div>
 <div class="card"><div class="cardhead"><div class="h3">Outcomes</div></div><div class="grid g2">${outcome('Positive',s.pos)}${outcome('Negative',neg,'not now or opt-out')}${outcome('Meetings',s.meetings)}${outcome('Qualified',s.qualified)}</div><hr class="s"><div class="small muted">Reply rate <b style="color:var(--ink)">${Math.round(s.replyRate*100)}%</b>, positive rate <b style="color:var(--ink)">${Math.round(s.posRate*100)}%</b>, meeting rate <b style="color:var(--ink)">${Math.round(s.meetRate*100)}%</b></div></div></div>
 <div class="card"><div class="cardhead"><div class="h3">Alerts</div></div><div class="row wrap gap16"><span class="chip ${conflictHeld?'line':''}">${ic('shield',13)}Held by conflict: ${conflictHeld}</span><span class="chip line">${ic('pause',13)}Jobs held: ${held}</span><span class="chip ${noRep?'':'line'}">${ic('users',13)}${noRep?'No active rep':'Rep assigned'}</span><span class="chip line">${ic('alert',13)}Failed jobs: ${fail}</span></div></div>`}
 </div>`;
}






function campConfig(c,ck){
 const num=(f,v,w)=>`<input class="inp sm" type="number" style="width:${w||90}px" min="0" data-i="cfg" data-id="${c.id}" data-f="${f}" value="${v}">`;
 const selq=(f,v)=>`<select class="sel sm" style="width:auto" data-i="cfg" data-id="${c.id}" data-f="${f}"><option value="0" ${!v?'selected':''}>Runs on its own</option><option value="1" ${v?'selected':''}>Needs approval</option></select>`;
 const ro=c.status==='completed';
 return`<div class="pad col gap16"><div class="banner info" style="font-weight:450">${ic('info',16)}Changes save as a new campaign version (now ${c.version}). They apply to the next job. Running jobs finish under the old version.</div>
 <div class="grid g2"><div class="card"><div class="cardhead"><div class="h3">Targeting</div></div><dl class="kv"><dt>ICP</dt><dd>${esc(c.icp)}</dd><dt>Personas</dt><dd>${esc(c.personas)}</dd><dt>Geography</dt><dd>${esc(c.geo)}</dd><dt>Exclusions</dt><dd>${(c.exclusions||[]).map(x=>`<span class="chip">${esc(x)}</span>`).join(' ')}</dd><dt>Signals</dt><dd>${esc(c.signals)}</dd><dt>Objective</dt><dd>${esc(c.objective)}</dd><dt>Channel order</dt><dd>${esc(c.order)}</dd></dl></div>
 <div class="card"><div class="cardhead"><div class="h3">Limits and approvals</div></div><div class="col gap12">
  <div class="row"><span class="grow">Daily send cap</span>${num('cap',c.cap)}</div><div class="row"><span class="grow">Qualify threshold</span>${num('thr',c.thr)}</div><div class="row"><span class="grow">Priority in conflicts</span>${num('priority',c.priority)}</div>
  ${['email','linkedin','sms','voice'].map(k=>`<div class="row"><span class="grow">${CH[k].n} daily limit</span>${num('lim_'+k,c.chLimit[k])}</div>`).join('')}
  <div class="row"><span class="grow">First touch</span>${selq('appr_first',c.appr.first)}</div><div class="row"><span class="grow">Voice calls</span>${selq('appr_voice',c.appr.voice)}</div><div class="row"><span class="grow">Pricing replies</span>${selq('appr_reply',c.appr.reply)}</div></div></div></div>
 <div class="card"><div class="cardhead"><div class="h3">Reps</div></div><div class="row wrap">${S.users.filter(u=>u.role==='Rep').map(u=>`<label class="row chip line" style="height:32px;cursor:pointer"><input type="checkbox" class="chk" data-i="cfgRep" data-id="${c.id}" data-u="${u.id}" ${c.reps.includes(u.id)?'checked':''} ${u.active?'':'disabled'}>${esc(u.name)} <span class="faint">${u.limit} a day</span></label>`).join('')}</div></div>
 ${c.status==='draft'?`<div class="card"><div class="cardhead"><div class="h3">Pre-launch checklist</div>${S.user.role!=='Rep'?`${(UI.dry||{})[c.id]?`<span class="spin" role="status" aria-label="Dry run in progress"></span><button class="btn sm dis" disabled>Running dry run</button>`:`<button class="btn sm" data-a="dryNow" data-id="${c.id}">${ic('play',14)}Run dry run</button>`}`:''}</div>${ckList(ck)}</div>`:''}</div>`;
}
/* ---------- create campaign ---------- */
function newCf(){
 const defaultReps=(typeof S!=='undefined'&&S&&S.users)?S.users.filter(u=>u.role==='Rep'&&u.active).slice(0,1).map(u=>u.id):[];
 const defaultDocs=(typeof S!=='undefined'&&S&&S.kb&&S.kb.docs)?S.kb.docs.filter(d=>d.scope==='C1'||d.scope==='global').map(d=>d.id):[];
 return{id:null,tpl:'C1',name:'',objective:'Automate internal tools intake and workflows',roles:'VP Engineering, Head of Platform, CTO',geo:'North America',exclusions:'Companies under 50 staff',size:'Series B to D',refs:'',agents:Object.fromEntries(AGENTS.map(a=>[a.k,true])),thr:70,channels:{email:true,linkedin:false,sms:false,voice:false},cap:30,first:false,voice:true,reply:true,tone:'Direct, technical, peer-to-peer without buzzwords.',docs:defaultDocs,reps:defaultReps,dry:null};
}
function cfFill(cf,k){const c=C(k);Object.assign(cf,{tpl:k,objective:c.objective,roles:c.roles.join(', '),geo:c.geoList.join(', '),exclusions:c.exclusions.join(', '),size:c.icp,tone:c.tone,thr:c.thr,cap:c.cap,first:c.appr.first,voice:c.appr.voice,reply:c.appr.reply,channels:Object.assign({},c.channels),reps:c.reps.slice(),docs:S.kb.docs.filter(d=>d.scope===k).map(d=>d.id),dry:null})}
function cfCk(cf){
 const split=s=>s.split(',').map(x=>x.trim()).filter(Boolean);
 const docs=S.kb.docs.filter(d=>cf.docs.includes(d.id)||d.scope==='global');const chunks=new Set();docs.forEach(d=>d.chunks.forEach(k=>chunks.add(k)));
 const hasCase=docs.some(d=>d.type==='case study'),hasObj=docs.some(d=>d.type==='objections');
 const chOk=Object.keys(cf.channels).filter(k=>cf.channels[k]&&S.integ[{email:'gmail',linkedin:'linkedin',sms:'twilio',voice:'voice'}[k]].status==='ok');
 const reps=cf.reps.map(U).filter(u=>u&&u.active&&u.limit>0);
 const key=JSON.stringify([cf.tpl,cf.roles,cf.geo,cf.exclusions,cf.tone,cf.docs,cf.channels]);
 return[
  {ok:split(cf.roles).length>0&&split(cf.geo).length>0&&split(cf.exclusions).length>0,t:'ICP has at least one role, one geography and one exclusion rule'},
  {ok:cf.tone.trim().length>10&&Object.values(cf.agents).some(Boolean),t:'Every enabled agent has an active prompt version (built from the tone and objective)'},
  {ok:chunks.size>=8&&hasCase&&hasObj,t:`At least 8 knowledge chunks, including one case study and one objection (${chunks.size} now)`},
  {ok:chOk.length>0,t:'At least one channel is enabled with a verified sender'},
  {ok:reps.length>0,t:'At least one rep is assigned, with limits set'},
  {ok:!!cf.dry&&cf.dry.ok&&cf.dry.key===key,t:'A dry run on 3 sample prospects passed the grounding check'}
 ];
}
function ckPanel(cf){
 const ck=cfCk(cf),vol=Math.min(+cf.cap||0,Object.values(cf.channels).filter(Boolean).length*12);const d=cf.dry;
 return`<div class="card" style="position:sticky;top:76px"><div class="cardhead"><div class="h3">Pre-launch checklist</div><span class="muted small">${ck.filter(x=>x.ok).length} of ${ck.length}</span></div>${ckList(ck)}
 <hr class="s"><div class="small muted">Projected volume: up to <b style="color:var(--ink)">${vol}</b> touches a day. Estimated model cost <b style="color:var(--ink)">${money(vol*0.056)}</b> a day at about ${money(0.056)} per prospect.</div>
 ${d&&d.run?`<hr class="s"><div class="row"><span class="spin"></span><span>Sample ${d.i} of 3</span></div>`:''}${d&&d.done?`<hr class="s"><div class="banner ${d.ok?'ok':'bad'}" style="font-weight:450;align-items:flex-start">${ic(d.ok?'check':'alert',16)}<span>${d.ok?'All 3 samples passed grounding.':`Dry run failed at the <b>${d.agent}</b>: ${esc(d.msg)}`}</span></div>${d.sample?`<div class="msg" style="font-size:13px;max-height:170px;overflow:auto">${esc(d.sample)}</div>`:''}`:''}
 ${ck.every(x=>x.ok)?'':'<div class="muted small" style="margin-top:12px">Activate stays off until every item passes.</div>'}</div>`;
}
function pgCreate(){
 if(!UI.cf)UI.cf=newCf();const cf=UI.cf;UI.open=UI.open||{};
 const sec=(k,t,body)=>`<details class="sec" data-sec="${k}" ${UI.open[k]===false?'':'open'}><summary>${t}${ic('down',16).replace('class="ic"','class="ic chev"')}</summary><div class="body col gap12">${body}</div></details>`;
 const f=(l,name,ph,hint,type)=>`<div class="field"><label>${l}</label><input class="inp" data-i="cf" data-f="${name}" value="${esc(cf[name])}" placeholder="${esc(ph||'')}">${hint?`<div class="hint">${hint}</div>`:''}</div>`;
 const libDocs=S.kb.docs.filter(d=>d.scope!=='global');
 return`${band({slim:true,crumbs:[['Campaigns','/campaigns'],['New campaign']],title:'Create campaign',sub:'Configure a campaign end to end. The checklist on the right tells you what blocks activation.',acts:`<button class="btn" data-a="cfDry">${ic('play',14)}Run dry run</button><button class="btn" data-a="cfSave">Save draft</button><button class="btn pri ${cfCk(cf).every(x=>x.ok)?'':'dis'}" id="cfAct" data-a="cfActivate">Activate</button><div class="field" style="min-width:220px"><select class="sel" data-i="cfTpl"><option value="">Start from a template</option><option value="C1">Start from US SaaS CTO</option><option value="C2">Start from India BFSI CIO</option><option value="C3">Start from US Voice AI founder</option></select></div>`})}
 <div class="pad"><div class="split"><div>
 ${sec('id','Identity',f('Campaign name','name','Example: UK Fintech CTOs')+f('Objective','objective','Book a 20-minute call on ...'))}
 ${sec('tg','Targeting',f('Roles (comma separated)','roles','CTO, VP Engineering')+f('Geography','geo','United States')+f('Company criteria','size','US B2B SaaS, 100 to 1,000 staff, Series B to D')+f('Exclusions (comma separated)','exclusions','Agencies, competitors, under 50 staff','Rules reject these before any model runs, at zero token cost.')+f('Reference profiles','refs','Northbeam, Ringlet','Customers whose profile the Qualifier should resemble.'))}
 ${sec('ag','Agents',`<div class="grid g2">${AGENTS.map(a=>`<div class="row"><div class="grow"><b style="font-weight:550">${a.k}</b><div class="small muted">${a.d}</div></div><button class="switch ${cf.agents[a.k]?'on':''}" data-a="cfAgent" data-k="${a.k}" role="switch" aria-checked="${!!cf.agents[a.k]}"></button></div>`).join('')}</div><div class="row"><span class="grow">Qualify threshold (score out of 100)</span><input class="inp sm" type="number" style="width:90px" data-i="cf" data-f="thr" value="${cf.thr}"></div>`)}
 ${sec('ch','Channels and limits',`<div class="grid g2">${['email','linkedin','sms','voice'].map(k=>`<div class="row"><div class="grow row gap4">${chIc(k)}<b style="font-weight:550">${CH[k].n}</b> ${modeTag(chanMode(k))}</div><button class="switch ${cf.channels[k]?'on':''}" data-a="cfChan" data-k="${k}" role="switch" aria-checked="${!!cf.channels[k]}"></button></div>`).join('')}</div>
  <div class="grid g2"><div class="field"><label>Daily send cap</label><input class="inp" type="number" data-i="cf" data-f="cap" value="${cf.cap}"></div><div class="field"><label>First touch</label><select class="sel" data-i="cfSel" data-f="first"><option value="0" ${!cf.first?'selected':''}>Runs on its own</option><option value="1" ${cf.first?'selected':''}>Needs approval</option></select></div><div class="field"><label>Voice calls</label><select class="sel" data-i="cfSel" data-f="voice"><option value="0" ${!cf.voice?'selected':''}>Runs on its own</option><option value="1" ${cf.voice?'selected':''}>Needs approval</option></select></div><div class="field"><label>Pricing replies</label><select class="sel" data-i="cfSel" data-f="reply"><option value="0" ${!cf.reply?'selected':''}>Runs on its own</option><option value="1" ${cf.reply?'selected':''}>Needs approval</option></select></div></div>`)}
 ${sec('pr','Prompts',`<div class="field"><label>Tone</label><textarea class="txt" rows="3" data-i="cf" data-f="tone" placeholder="Concise, technical, peer to peer, under 90 words">${esc(cf.tone)}</textarea><div class="hint">The system prompt and seven role prompts are built from your tone and objective as version 1. Edit each one later under Prompts.</div></div>`)}
 ${sec('kb','Knowledge',`<div class="muted small">Global knowledge always applies. Attach campaign documents to give the Writer and Responder something to cite.</div><div class="col">${libDocs.map(d=>`<label class="row" style="cursor:pointer"><input type="checkbox" class="chk" data-i="cfDoc" data-id="${d.id}" ${cf.docs.includes(d.id)?'checked':''}><span class="grow">${esc(d.name)} <span class="faint small">${d.chunks.length} chunks, from ${d.scope}</span></span><span class="chip">${d.type}</span></label>`).join('')}</div>`)}
 ${sec('rp','Reps',`<div class="col">${S.users.filter(u=>u.role==='Rep').map(u=>`<label class="row" style="cursor:pointer"><input type="checkbox" class="chk" data-i="cfRep" data-id="${u.id}" ${cf.reps.includes(u.id)?'checked':''} ${u.active?'':'disabled'}>${av(u.name,'sm')}<span class="grow">${esc(u.name)} <span class="faint small">${u.hours}, ${u.limit} a day</span></span></label>`).join('')}</div>`)}
 </div><div id="ckpanel">${ckPanel(cf)}</div></div></div>`;
}




/* ---------- create campaign actions ---------- */
function refreshCk(){const p=$('#ckpanel');if(p)p.innerHTML=ckPanel(UI.cf);const b=$('#cfAct');if(b)b.classList.toggle('dis',!cfCk(UI.cf).every(x=>x.ok))}
ACT.cfAgent=t=>{UI.cf.agents[t.dataset.k]=!UI.cf.agents[t.dataset.k];t.classList.toggle('on');refreshCk()};
ACT.cfChan=t=>{UI.cf.channels[t.dataset.k]=!UI.cf.channels[t.dataset.k];t.classList.toggle('on');refreshCk()};



/* ---------- prospects ---------- */
function whyText(e){const p=P(e.pid);
 if(e.reject)return e.reject;
 if(e.st==='new')return 'Discovered from the lead source. Research is queued.';
 const hook=p.facts.find(f=>f.src==='careers'||f.src==='news'||f.src==='product'||f.src==='rbi')||p.facts[0];
 return hook?hook.text:'No facts on file yet.';
}
function lastTouchT(e){const m=msgsOf(e).filter(x=>x.status==='sent').sort((a,b)=>b.t-a.t)[0];return m?m.t:null}
function colOf(e){const s=e.st;if(['rejected','opted_out','stopped'].includes(s))return 6;return (STATE[s]||STATE.new).st}
function prospectsView(cid){
 const F=UI.fil;const q=(F.pq||'').toLowerCase();const params=qs();const repF=params.get('rep')||F.prep||'';const me=S.user;
 let list=S.enr.filter(e=>C(e.cid).status!=='archived');
 if(cid)list=list.filter(e=>e.cid===cid);else if(F.pc)list=list.filter(e=>e.cid===F.pc);
 if(me.role==='Rep')list=list.filter(e=>C(e.cid).reps.includes(me.id));
 if(F.ps)list=list.filter(e=>e.st===F.ps);
 if(F.pscore)list=list.filter(e=>(e.score||0)>=+F.pscore);
 if(F.pch)list=list.filter(e=>msgsOf(e).some(m=>m.ch===F.pch));
 if(F.pconf)list=list.filter(e=>S.conflicts.some(x=>x.pid===e.pid&&x.cids.includes(e.cid)&&x.status!=='resolved'));
 if(repF)list=list.filter(e=>repFor(e).id===repF);
 if(q)list=list.filter(e=>{const p=P(e.pid);return(p.name+' '+p.company+' '+p.title+' '+e.cid).toLowerCase().includes(q)});
 const view=F.pview||(cid?'board':'table');
 const tools=`<div class="filters" style="margin-bottom:16px"><input class="inp" id="pq" style="min-width:220px" placeholder="Search name, company or title" data-i="pq" value="${esc(F.pq||'')}">
 ${cid?'':`<select class="sel" data-i="pc"><option value="">All campaigns</option>${S.camps.map(c=>`<option value="${c.id}" ${F.pc===c.id?'selected':''}>${c.id} ${esc(c.name)}</option>`).join('')}</select>`}
 <select class="sel" data-i="ps"><option value="">Any state</option>${Object.keys(STATE).map(k=>`<option value="${k}" ${F.ps===k?'selected':''}>${STATE[k].l}</option>`).join('')}</select>
 <select class="sel" data-i="pscore"><option value="">Any score</option><option value="50" ${F.pscore==='50'?'selected':''}>50 and up</option><option value="70" ${F.pscore==='70'?'selected':''}>70 and up</option><option value="85" ${F.pscore==='85'?'selected':''}>85 and up</option></select>
 <select class="sel" data-i="pch"><option value="">Any channel</option>${Object.keys(CH).map(k=>`<option value="${k}" ${F.pch===k?'selected':''}>${CH[k].n}</option>`).join('')}</select>
 <label class="row chip line" style="height:34px;cursor:pointer"><input type="checkbox" class="chk" data-i="pconf" ${F.pconf?'checked':''}>Has conflict</label>
 ${repF?`<span class="chip">${esc(U(repF).name)} <button class="btn ghost xs" data-a="clearRep" aria-label="Clear">${ic('x',12)}</button></span>`:''}
 <span class="right"></span><div class="seg"><button class="${view==='table'?'on':''}" data-a="pview" data-k="table">${ic('grid',14)}Table</button><button class="${view==='board'?'on':''}" data-a="pview" data-k="board">${ic('layers',14)}Board</button></div>
 ${S.user.role!=='Rep'?`<button class="btn sm" data-a="discoverAny" ${cid?'data-id="'+cid+'"':''}>${ic('search',14)}Simulate discovery</button>`:''}</div>`;
 if(!list.length)return tools+empty('No prospects yet','Run discovery or import a CSV. Filters can also hide everything.',`<br><button class="btn pri" data-a="discoverAny" ${cid?'data-id="'+cid+'"':''}>Simulate discovery</button>`);
 if(view==='board'){
  const cols=['Discovered','Researched','Qualified','Contacted','Engaged','Meeting','Stopped'];
  return tools+`<div class="board">${cols.map((cn,i)=>{const es=list.filter(e=>colOf(e)===i);return`<div><div class="colhead"><h3>${cn}</h3><span class="cnt">${es.length}${ic('sort',14)}</span></div>${es.slice(0,40).map(e=>{const p=P(e.pid),lt=lastTouchT(e),n=msgsOf(e).length;const na=nextAction(e);
   return`<button class="kcard hv ${i===6?'closed':''} ${C(e.cid).status==='paused'?'paused':''}" data-go="/prospects/${p.id}?c=${e.cid}"><div class="t"><span class="trunc">${esc(p.name)}</span><span class="more">${ic('dots',16)}</span></div><p>${esc(p.title)}, ${esc(p.company)}. ${e.st==='rejected'?esc(e.reject):spillText(e.st)}</p><div class="foot"><span class="fchip">${ic('calendar',13)}${lt?fD(lt).slice(4):'No touch'}</span><span class="fchip q">${ic('msg',13)}${n}</span><span class="fchip q">${ic('target',13)}${e.score==null?(e.st==='rejected'?'Rule':'-'):e.score}</span>${cid?'':campChip(e.cid)}</div><div class="detail"><div>${esc(p.email)}</div><div class="row gap4" style="margin-top:6px">${ic('route',13)}${esc(na.x)}</div><div class="row gap4" style="margin-top:4px">${ic('user',13)}${esc(repFor(e).name)}</div></div></button>`}).join('')}${es.length>40?`<div class="muted small">${es.length-40} more. Narrow the filters to see them.</div>`:''}${es.length?'':'<div class="empty" style="padding:22px">Empty</div>'}</div>`}).join('')}</div>`;
 }
 const rows=list.slice(0,120).map(e=>{const p=P(e.pid),lt=lastTouchT(e),na=nextAction(e);const others=enrOf(p.id).filter(x=>x!==e);
  return`<tr class="click" data-go="/prospects/${p.id}?c=${e.cid}"><td><div class="row">${av(p.name)}<div><b style="font-weight:550">${esc(p.name)}</b><div class="small muted">${esc(p.title)}</div></div></div></td><td>${esc(p.company)}<div class="small muted">${p.staff.toLocaleString('en-US')} staff, ${esc(p.city)}</div></td><td>${campChip(e.cid)}${others.map(o=>campChip(o.cid)).join('')}</td><td>${spill(e.st)}</td><td>${scoreBar(e.score,e)}</td><td style="max-width:230px" class="small muted"><div class="trunc" title="${esc(whyText(e))}">${esc(whyText(e))}</div></td><td class="small">${lt?rel(lt):'Not contacted'}</td><td class="small">${esc(na.x)}</td><td class="small">${esc(first(repFor(e).name))}</td></tr>`}).join('');
 return tools+`<div class="tblwrap"><table class="tbl"><thead><tr><th>Prospect</th><th>Company</th><th>Campaign</th><th>State</th><th>ICP score</th><th>Why this prospect</th><th>Last touch</th><th>Next action</th><th>Rep</th></tr></thead><tbody>${rows}</tbody></table></div><div class="muted small" style="margin-top:10px">${Math.min(list.length,120)} of ${list.length} shown. Every record is fictional ${demoTag}</div>`;
}
function pgProspects(){
 return`${band({crumbs:[['Command Center','/overview'],['Prospects']],title:'Prospects',sub:'Find any person across every campaign. Open one to see everything the system knows and why it acted.'})}<div class="pad">${prospectsView(null)}</div>`;
}
ACT.pview=t=>{UI.fil.pview=t.dataset.k;repaint()};
ACT.clearRep=()=>{UI.fil.prep='';UI.path=UI.path.split('?')[0];try{location.hash='#'+UI.path}catch(e){}repaint()};

/* ---------- prospect detail ---------- */
function pgProspect(pid){
 const p=P(pid);if(!p)return`<div class="pad">${empty('Prospect not found','Check the link or search again.','<br><button class="btn pri" data-go="/prospects">Prospects</button>')}</div>`;
 const enrs=enrOf(pid).filter(e=>S.user.role!=='Rep'||C(e.cid).reps.includes(S.user.id));if(!enrs.length)return deny('This prospect belongs to campaigns you do not work on.');
 const cq=qs().get('c');const e=enrs.find(x=>x.cid===(UI.sel.enr&&UI.sel.enrP===pid?UI.sel.enr:cq))||enrs[0];UI.sel.enr=e.cid;UI.sel.enrP=pid;
 const c=C(e.cid);const rep=repFor(e);
 const facts=p.facts.map(f=>`<div class="row" style="align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--line2)"><div class="grow small">${esc(f.text)}<div style="margin-top:4px"><a class="why" data-a="openFact" data-id="${f.id}">${esc(f.url)}</a></div></div><span class="conf ${f.conf}">${f.conf}</span></div>`).join('');
 const sup=p.suppressed;
 const items=[];
 msgsOf({id:'x'});S.msgs.filter(m=>m.pid===pid&&S.user).forEach(m=>{if(enrs.some(x=>x.id===m.eid))items.push({t:m.t,m})});
 S.acts.filter(a=>a.pid===pid&&!['send','reply','draft'].includes(a.kind)&&enrs.some(x=>x.id===a.eid)).forEach(a=>items.push({t:a.t,a}));
 items.sort((a,b)=>b.t-a.t);
 const ap=S.approvals.filter(a=>a.eid===e.id&&a.status==='open');
 const tl=items.map(it=>{
  if(it.a){const a=it.a;return`<div class="tli"><span class="ico">${ic(ICO[a.kind]||'spark',15)}</span><div class="grow"><div class="row wrap"><b style="font-weight:550">${esc(a.text)}</b>${a.cid&&enrs.length>1?campChip(a.cid):''}</div><div class="small faint">${esc(a.agent||'System')}, ${fDT(a.t)}${a.runId?` <button class="why" data-a="trace" data-id="${a.runId}">Why</button>`:''}</div></div></div>`}
  const m=it.m;const out=m.dir==='out';const pend=m.status==='pending'||m.status==='rejected';
  const who=m.human?`${esc(m.by)} (rep)`:out?'Cadence':esc(p.first);
  const apItem=pend&&ap.find(x=>x.msgId===m.id);
  return`<div class="tli"><span class="ico ${out?'out':''}">${chIc(m.ch)}</span><div class="grow"><div class="row wrap"><b style="font-weight:550">${who}${m.dir==='in'?' replied':m.kind==='call'?' called':pend?' drafted':' sent'}</b><span class="chip line">${CH[m.ch].n}</span>${modeTag(m.mode)}${enrs.length>1?campChip(m.cid):''}${m.seed?demoTag:''}${pend?`<span class="pill ${m.status==='rejected'?'bad':'warn'}">${m.status==='rejected'?'Rejected':'Pending approval'}</span>`:''}</div>
  <div class="msg ${out?'':'in'} ${pend?'draft':''}">${m.subject?`<div class="subj">${esc(m.subject)}</div>`:''}${esc(m.body)}</div>
  <div class="row wrap small" style="margin-top:6px"><span class="faint">${fDT(m.t)}</span>${m.runId?`<button class="why" data-a="trace" data-id="${m.runId}">Why</button>`:''}${m.cls?`<span class="chip">${m.cls==='escalate'?ESC[m.sub]:m.cls==='not_now'?'Not now':cap(m.cls)}</span><span class="faint">${esc(m.rule||'')}</span>`:''}${m.kind==='call'?`<button class="why" data-a="callView" data-id="${m.eid}">Open transcript</button>`:''}${apItem?`<button class="btn xs pri" data-a="approvePd" data-id="${apItem.id}">Approve</button><button class="btn xs" data-a="rejectAsk" data-id="${apItem.id}">Reject</button>`:''}</div></div></div>`}).join('');
 const plan=(e.plan||[]).map(s=>`<div class="row" style="align-items:flex-start;padding:9px 0;border-bottom:1px solid var(--line2)"><span class="ico" style="width:28px;height:28px;border-radius:9px;background:var(--mist);display:grid;place-items:center">${chIc(s.ch)}</span><div class="grow small"><b style="font-weight:550">Day ${s.day}: ${CH[s.ch].n} ${s.purpose.replace('_',' ')}</b>${s.replanned?' <span class="chip warn" style="height:18px;background:var(--warn-bg);color:var(--warn)">Replanned</span>':''}<div class="muted">${esc(s.reason)}</div></div><div class="tar small"><span class="pill ${s.status==='done'?'done':s.status==='pending'?'info':'paused'}" style="height:20px;font-size:11.5px">${s.status}</span><div class="faint" style="margin-top:2px">${s.status==='pending'?rel(s.due):s.doneAt?fD(s.doneAt):''}</div></div></div>`).join('');
 const hist=(e.planHist||[]).map(h=>`<div class="small" style="padding:8px 0"><div class="faint">${fDT(h.t)}: ${esc(h.why)}</div><div class="row" style="margin-top:4px"><s class="muted">${esc(h.old.join(', '))}</s></div><div>${esc(h.now.join(', '))}</div></div>`).join('');
 const conf=S.conflicts.filter(x=>x.pid===pid);const es_=S.escal.filter(x=>enrs.some(y=>y.id===x.eid));
 const notices=[];
 if(sup)notices.push(`<div class="banner bad" style="font-weight:450;align-items:flex-start">${ic('stop',16)}<span><b>Suppressed.</b> This person opted out. No campaign may contact them.</span></div>`);
 const cl=S.claims[pid];if(cl)notices.push(`<div class="banner mist" style="font-weight:450;align-items:flex-start">${ic('shield',16)}<span><b>${cl.cid} holds the claim</b> since ${fD(cl.since)}.${enrs.length>1?' Other campaigns wait.':''}</span></div>`);
 conf.forEach(x=>notices.push(`<div class="banner paused" style="font-weight:450;align-items:flex-start">${ic('shield',16)}<span><b>${x.cids.join(' vs ')}:</b> ${esc(x.decision)}. Rule: ${esc(x.rule)}.</span></div>`));
 if(e.hold)notices.push(`<div class="banner paused" style="font-weight:450;align-items:flex-start">${ic('clock',16)}<span>Next send held: <b class="mono">${e.hold.code}</b>${e.hold.until?', until '+fDT(e.hold.until):''}.</span></div>`);
 if(e.deferNote)notices.push(`<div class="banner paused" style="font-weight:450;align-items:flex-start">${ic('shield',16)}<span>Deferred in ${e.cid}: ${esc(e.deferNote)}</span></div>`);
 es_.filter(x=>x.status==='open').forEach(x=>notices.push(`<div class="banner paused" style="font-weight:450;align-items:flex-start">${ic('handoff',16)}<span>Escalated: ${ESC[x.reason]}. <a class="why" data-go="/approvals">Open in inbox</a></span></div>`));
 const na=nextAction(e);const stopped=['rejected','opted_out','stopped','meeting'].includes(e.st);
 return`${band({crumbs:[['Prospects','/prospects'],[esc(p.name)]],title:`<span class="row" style="gap:14px">${av(p.name,'lg')}<span>${esc(p.name)}</span></span>`,sub:`${esc(p.title)} at ${esc(p.company)}, ${esc(p.city)}`,acts:`${e.st==='new'?`<button class="btn pri" data-a="runNow" data-id="${e.id}">${ic('play',15)}Run now</button>`:''}<button class="btn" data-a="simReply" data-id="${e.id}">${ic('msg',15)}Simulate reply</button>${stopped?'':`<button class="btn" data-a="escalateMan" data-id="${e.id}">${ic('handoff',15)}Escalate to rep</button><button class="btn" data-a="stopP" data-id="${e.id}">${ic('stop',15)}Stop this prospect</button>`}`,extra:`<div class="row wrap" style="margin-top:14px">${enrs.map(x=>`<button class="chip ${x.cid===e.cid?cc(x.cid):'line'}" style="border:0;cursor:pointer;height:30px;font-size:13px" data-a="selEnr" data-c="${x.cid}"><i class="dot ${cc(x.cid)}"></i>${x.cid} ${esc(C(x.cid).name)}: ${spillText(x.st)}</button>`).join('')}${demoTag}</div>`})}
 <div class="pad"><div class="grid" style="grid-template-columns:300px minmax(0,1fr) 340px;align-items:start;gap:20px" id="pdgrid">
 <div class="col gap16"><div class="card"><div class="cardhead"><div class="h3">Profile</div></div><dl class="kv" style="grid-template-columns:78px 1fr"><dt>Email</dt><dd class="small" style="word-break:break-all">${esc(p.email)}</dd><dt>LinkedIn</dt><dd class="small">${esc(p.linkedin)}</dd><dt>Phone</dt><dd class="small">${esc(p.phone)}</dd><dt>Company</dt><dd class="small">${esc(p.ind)||'Existing customer'}, ${p.staff.toLocaleString('en-US')} staff${p.stage&&p.stage!=='n/a'?', '+esc(p.stage):''}</dd><dt>Rep</dt><dd class="small">${esc(rep.name)}</dd></dl>${p.bio?`<div class="banner bad" style="margin-top:12px;font-weight:450;align-items:flex-start">${ic('shield',16)}<span>Bio contains instruction-like text. The Guardian strips it before any model reads it: <i>"${esc(p.bio)}"</i></span></div>`:''}</div>
 <div class="card"><div class="cardhead"><div class="h3">Facts on file</div><span class="muted small">${p.facts.length}</span></div>${facts||'<div class="muted small">No facts yet. The Researcher has not found sources, so no message will cite anything.</div>'}</div></div>
 <div><div class="card"><div class="cardhead"><div class="h3">Timeline across channels</div><span class="muted small">${items.length} events</span></div>${ap.length&&!items.some(i=>i.m&&i.m.status==='pending')?`<div class="banner paused" style="margin-bottom:14px">${ic('edit',16)}<span>An approval is open for this prospect.</span><button class="btn sm right" data-go="/approvals">Open</button></div>`:''}${items.length?`<div class="tl">${tl}</div>`:empty('Not contacted','Next step: research (queued).')}</div></div>
 <div class="col gap16"><div class="card"><div class="cardhead"><div class="h3">Next actions</div></div><div class="banner ${stopped?'mist':'info'}" style="margin-bottom:8px;font-weight:450">${ic('route',16)}<span>${esc(na.x)}</span></div>${plan||'<div class="muted small">The Sequencer has not planned touches yet.</div>'}${hist?`<div class="lbl" style="margin-top:14px">Plan changes</div>${hist}`:''}</div>
 <div class="card"><div class="cardhead"><div class="h3">ICP scorecard</div>${e.score!=null?`<span class="pill ${e.score>=c.thr?'live':'warn'}">${e.score}</span>`:'<span class="pill bad">Rule reject</span>'}</div>${e.crit?scorecard(e,e.crit,true):'<div class="muted small">Scoring starts after research.</div>'}</div>
 ${notices.length?`<div class="col">${notices.join('')}</div>`:''}</div></div></div>`;
}
ACT.selEnr=t=>{UI.sel.enr=t.dataset.c;const pid=UI.path.split('/')[2].split('?')[0];UI.path='/prospects/'+pid+'?c='+t.dataset.c;repaint()};




ACT.presetR=t=>{$('#srt').value=t.dataset.t};
/* ---------- agent activity ---------- */
function activityView(cid){
 const F=UI.fil;const camp=cid||F.actc||'';const st=F.acts||'';
 let jobs=S.jobs.filter(j=>(!camp||j.cid===camp));
 if(st)jobs=jobs.filter(j=>{const s=jobState(j);return st==='held'?s==='held':st==='queued'?(s==='queued'||s==='scheduled'):j.status===st});
 jobs=jobs.slice().sort((a,b)=>(b.end||b.at||0)-(a.end||a.at||0)).slice(0,60);
 const all=S.jobs.filter(j=>!camp||j.cid===camp);
 const cnt={running:0,queued:0,held:0,failed:0};all.forEach(j=>{const s=jobState(j);if(s==='running')cnt.running++;else if(s==='queued'||s==='scheduled')cnt.queued++;else if(s==='held')cnt.held++;else if(j.status==='failed')cnt.failed++});
 const swc=cid||F.swc||'C1';const c=C(swc);
 const rows=jobs.map(j=>{const p=j.pid&&P(j.pid);const s=jobState(j);const pill={done:'<span class="pill done">Done</span>',running:`<span class="pill info"><span class="spin" style="width:11px;height:11px"></span>Running</span>`,queued:'<span class="pill info">Queued</span>',scheduled:`<span class="pill info">Scheduled ${j.due?rel(j.due):''}</span>`,held:`<span class="pill paused">${ic('pause',11)}Held</span> <span class="faint small mono">${heldReason(j)}</span>`,failed:'<span class="pill bad">Failed</span>',cancelled:'<span class="pill done">Cancelled</span>'}[s]||'';
  const sum=j.sum||(j.status==='queued'?({research:'Research prospect',qualify:'Score against ICP',plan:'Plan the sequence',draft:'Draft and gate the touch',reply:'Answer the reply',call:'Place the call'})[j.step]:j.err||'');
  return`<tr class="click ${s==='held'?'held':''}" data-a="trace" data-id="${j.id}"><td class="small muted" style="white-space:nowrap">${fTs(j.end||j.at)}</td><td>${campChip(j.cid)}</td><td style="white-space:nowrap"><b style="font-weight:550">${j.agent}</b>${j.replay?' <span class="tag replay">REPLAY</span>':''}</td><td style="white-space:nowrap">${p?esc(p.name):''}</td><td class="small" style="min-width:260px">${esc(sum)}</td><td>${pill}</td><td class="small">${j.dur?j.dur+'s':''}</td><td class="small">${j.cost!=null&&j.status==='done'?money(j.cost):''}</td><td class="tar">${j.status==='failed'?`<button class="btn xs" data-a="retry" data-id="${j.id}">Retry</button>`:''}</td></tr>`}).join('');
 const sparks=S.camps.filter(x=>!camp||x.id===camp).map(x=>`<div class="row"><span style="width:52px">${campChip(x.id)}</span>${spark((S.qh||{})[x.id],140,26)}<span class="small muted">${S.jobs.filter(j=>j.cid===x.id&&(j.status==='queued')).length} in queue</span></div>`).join('');
 return`<div class="pad col gap16">
 <div class="kpirow">${[['Running',cnt.running],['Queued',cnt.queued],['Held',cnt.held],['Failed',cnt.failed]].map(x=>`<div class="tile ${x[0]==='Failed'&&x[1]?'err':''}" style="cursor:default"><b>${x[1]}</b><span>${x[0]}</span></div>`).join('')}</div>
 <div class="filters"><select class="sel" data-i="actc" ${cid?'disabled':''}><option value="">All campaigns</option>${S.camps.map(x=>`<option value="${x.id}" ${camp===x.id?'selected':''}>${x.id} ${esc(x.name)}</option>`).join('')}</select><select class="sel" data-i="acts"><option value="">Any status</option>${['queued','running','held','done','failed'].map(k=>`<option value="${k}" ${st===k?'selected':''}>${cap(k)}</option>`).join('')}</select><span class="right muted small">Refreshes every few seconds</span></div>
 <div class="grid g2"><div class="card"><div class="cardhead"><div class="h3">Agent switches</div>${cid?'':`<select class="sel sm" style="width:auto" data-i="swc">${S.camps.map(x=>`<option value="${x.id}" ${swc===x.id?'selected':''}>${x.id} ${esc(x.name)}</option>`).join('')}</select>`}</div><div class="grid g2" style="gap:10px 24px">${AGENTS.map(a=>`<div class="row"><div class="grow"><b style="font-weight:550">${a.k}</b><div class="small faint">${a.host}</div></div>${sw(c.agents[a.k],'agentSw','data-id="'+c.id+'" data-k="'+a.k+'"',c.status==='draft')}</div>`).join('')}</div><div class="muted small" style="margin-top:10px">Turn an agent off and its jobs wait. The rest of the campaign keeps running where the flow allows.</div></div>
 <div class="card"><div class="cardhead"><div class="h3">Queue depth</div></div><div class="col gap12">${sparks}</div></div></div>
 ${jobs.length?`<div class="tblwrap" style="max-height:640px;overflow:auto"><table class="tbl"><thead><tr><th>Time</th><th>Campaign</th><th>Agent</th><th>Prospect</th><th>Action</th><th>Status</th><th>Time taken</th><th>Cost</th><th></th></tr></thead><tbody id="runrows">${rows}</tbody></table></div>`:empty('No runs yet','Activate a campaign and the agents start working.')}</div>`;
}
function pgActivity(){return`${band({slim:true,crumbs:[['Command Center','/overview'],['Agent Activity']],title:'Agent Activity',sub:'Watch the agents work. Pause one campaign and its rows switch to held while the others keep moving.'})}${activityView(null)}`}
/* ---------- conversations ---------- */
function threadList(){
 const me=S.user;const ids=new Set();S.msgs.filter(m=>m.dir==='in').forEach(m=>ids.add(m.eid));S.escal.forEach(x=>ids.add(x.eid));S.approvals.filter(a=>a.status==='open'&&(a.kind==='reply')).forEach(a=>ids.add(a.eid));
 let l=[...ids].map(E).filter(Boolean).filter(e=>me.role!=='Rep'||C(e.cid).reps.includes(me.id));
 const f=UI.fil.cf||'all';
 l=l.filter(e=>f==='all'?true:f==='reply'?(S.escal.some(x=>x.eid===e.id&&x.status==='open')||S.approvals.some(a=>a.eid===e.id&&a.status==='open')):f==='positive'?['replied_pos','meeting'].includes(e.st):f==='objection'?['replied_obj','escalated'].includes(e.st):f==='notnow'?['replied_notnow','opted_out'].includes(e.st):true);
 return l.sort((a,b)=>lastMsgT(b)-lastMsgT(a));
}
function lastMsgT(e){const m=msgsOf(e).filter(x=>x.status!=='rejected').sort((a,b)=>b.t-a.t)[0];return m?m.t:0}
function sentiment(e){return({replied_pos:['Positive','live'],meeting:['Meeting','live'],replied_obj:['Objection','info'],escalated:['Escalated','warn'],replied_notnow:['Not now','done'],opted_out:['Opted out','bad']})[e.st]||['Open','done']}
function pgConversations(eid){
 const list=threadList();const cur=E(eid)||list.find(e=>e.id===UI.sel.thr)||list[0];if(cur)UI.sel.thr=cur.id;
 const f=UI.fil.cf||'all';
 const left=list.map(e=>{const p=P(e.pid),m=msgsOf(e).sort((a,b)=>b.t-a.t)[0],s=sentiment(e);return`<div class="item ${cur&&cur.id===e.id?'on':''}" data-go="/conversations/${e.id}">${av(p.name)}<div class="grow" style="min-width:0"><div class="row"><b>${esc(p.name)}</b><span class="right faint small">${rel(m.t)}</span></div><div class="small muted trunc">${esc(m.body.replace(/\n/g,' '))}</div><div class="row" style="margin-top:4px">${campChip(e.cid)}<span class="pill ${s[1]}" style="height:20px;font-size:11.5px">${s[0]}</span></div></div></div>`}).join('');
 let mid='',right='';
 if(cur){
  const p=P(cur.pid),ms=msgsOf(cur).filter(m=>m.status!=='rejected').sort((a,b)=>a.t-b.t);
  const escOpen=S.escal.find(x=>x.eid===cur.id&&x.status==='open');
  const lastOut=ms.filter(m=>m.dir==='out'&&m.segs&&m.status!=='rejected').slice(-1)[0];
  const human=UI.sel.take===cur.id;
  mid=`<div class="card" style="padding:0"><div class="row" style="padding:16px 18px;border-bottom:1px solid var(--line)"><div><div class="h3">${esc(p.name)}</div><div class="small muted">${esc(p.title)}, ${esc(p.company)}</div></div>${campChip(cur.cid)}<span class="right"></span><button class="btn sm" data-go="/prospects/${p.id}?c=${cur.cid}">Open prospect</button><button class="btn sm" data-a="simReply" data-id="${cur.id}">Simulate reply</button>${chanMode('linkedin')==='live'?`<button class="btn sm" data-a="liPaste" data-id="${cur.id}">Paste LinkedIn reply</button>`:''}</div>
  <div style="padding:18px;max-height:560px;overflow:auto">${ms.map(m=>{const out=m.dir==='out';return`<div style="display:flex;flex-direction:column;align-items:${out?'flex-end':'flex-start'};margin-bottom:14px"><div class="small faint row gap4" style="margin-bottom:4px">${chIc(m.ch)}${CH[m.ch].n} ${modeTag(m.mode)} ${fDT(m.t)}${m.human?' by '+esc(m.by):''}</div><div class="msg ${out?'':'in'} ${m.status==='pending'?'draft':''}" style="max-width:86%;margin:0">${m.subject?`<div class="subj">${esc(m.subject)}</div>`:''}${esc(m.body)}${m.status==='pending'?'<div class="small" style="margin-top:6px;color:var(--pause)">Pending approval</div>':''}</div><div class="small row gap4" style="margin-top:4px">${m.runId?`<button class="why" data-a="trace" data-id="${m.runId}">Why</button>`:''}${m.cls?`<span class="chip">${m.cls==='escalate'?ESC[m.sub]:cap(m.cls.replace('_',' '))}</span>`:''}${m.kind==='call'?`<button class="why" data-a="callView" data-id="${cur.id}">Open transcript</button>`:''}</div></div>`}).join('')}</div>
  <div style="padding:14px 18px;border-top:1px solid var(--line)">${human?`<textarea class="txt" id="humanText" rows="3" placeholder="Write as ${esc(S.user.name)}"></textarea><div class="row" style="margin-top:10px"><button class="btn pri" data-a="humanSend" data-id="${cur.id}">${ic('send',15)}Send reply</button><button class="btn" data-a="takeOff">Hand back to agents</button></div>`:`<div class="row"><span class="muted small grow">${['meeting','opted_out'].includes(cur.st)?'This thread is closed.':'Agents answer this thread. Take over to reply yourself.'}</span>${escOpen?`<button class="btn" data-go="/approvals">Open escalation</button>`:''}<button class="btn pri" data-a="take" data-id="${cur.id}">Take over thread</button></div>`}</div></div>`;
  const sug=escOpen?`<div class="card"><div class="cardhead"><div class="h3">Suggested reply</div></div><div class="msg" style="margin-top:0">${esc(escOpen.suggested)}</div><button class="btn sm" style="margin-top:10px" data-a="useSug" data-id="${cur.id}" data-e="${escOpen.id}">Use this reply</button></div>`:'';
  right=`<div class="grid g2" style="align-items:start"><div class="card"><div class="cardhead"><div class="h3">Evidence</div></div>${lastOut?`<div class="small muted" style="margin-bottom:8px">Latest agent message, claim by claim.</div>${evidenceBlock(lastOut.segs,true)}`:'<div class="muted small">No agent-written message with sources in this thread yet.</div>'}</div>${sug}</div>`;
 }
 return`${band({slim:true,crumbs:[['Command Center','/overview'],['Conversations']],title:'Conversations',sub:'Read and act on threads. Every channel with one person sits in one thread.'})}
 <div class="pad"><div class="filters" style="margin-bottom:16px"><div class="seg">${[['all','All'],['reply','Needs a person'],['positive','Positive'],['objection','Objection'],['notnow','Not now']].map(x=>`<button class="${f===x[0]?'on':''}" data-a="thrFil" data-k="${x[0]}">${x[1]}</button>`).join('')}</div></div>
 ${list.length?`<div class="grid" style="grid-template-columns:320px minmax(0,1fr);align-items:start;gap:20px"><div class="card tight" style="padding:8px;max-height:760px;overflow:auto">${left}</div><div class="col gap16">${mid}${right}</div></div>`:empty('No conversations yet','Replies appear here. Use Simulate reply on any prospect to see one.')}</div>`;
}
ACT.thrFil=t=>{UI.fil.cf=t.dataset.k;UI.sel.thr=null;repaint()};
ACT.take=t=>{UI.sel.take=t.dataset.id;repaint()};ACT.takeOff=()=>{UI.sel.take=null;repaint()};

ACT.useSug=t=>{UI.sel.take=t.dataset.id;repaint();const x=S.escal.find(v=>v.id===t.dataset.e);const ta=$('#humanText');if(ta)ta.value=x.suggested};
ACT.callView=t=>{const e=E(t.dataset.id);const call=S.calls.find(c=>c.eid===e.id);if(!call){toast('No call transcript for this prospect.',{bad:true});return}
 const tag={Question:'info',Pricing:'warn',Objection:'paused',Positive:'live'};
 const counts={};call.tr.forEach(x=>{if(x[3])counts[x[3]]=(counts[x[3]]||0)+1});
 openModal(`<div class="row"><h2>Call with ${esc(P(e.pid).name)}</h2>${modeTag(call.mode)}<span class="right"></span><button class="btn ghost sm" data-a="closeModal">${ic('x',16)}</button></div><div class="row wrap" style="margin:10px 0"><span class="chip line">${ic('clock',12)}${call.dur}</span><span class="pill live">${call.disposition}</span>${Object.keys(counts).map(k=>`<span class="pill ${tag[k]}">${k} (${counts[k]})</span>`).join('')}</div>
 <div class="banner mist" style="font-weight:450;margin-bottom:12px">${esc(call.summary)}</div><div class="col gap12" style="max-height:380px;overflow:auto">${call.tr.map(x=>`<div class="row" style="align-items:flex-start"><span class="mono faint" style="width:44px">00:${String(x[1]).padStart(2,'0')}</span><div class="grow"><b style="font-weight:550">${x[0]}</b> ${x[3]?`<span class="pill ${tag[x[3]]}" style="height:20px;font-size:11.5px">${x[3]}</span>`:''}<div>${esc(x[2])}</div></div></div>`).join('')}</div>`,'lg')};

/* ---------- prompts and harness ---------- */
function pver(cid,role){return S.prompts.filter(p=>p.cid===cid&&p.role===role).sort((a,b)=>b.v-a.v)}
function lintPrompt(text){const out=[];[[/guarantee|100%|revolutionary|best-in-class|game-changing/i,'Uses a banned claim word'],[/(offer|give|promise|grant)[^.\n]{0,24}discount/i,'Promises a discount, which breaks global rule G4'],[/ignore (all |any )?(previous|prior)/i,'Contains override language'],[/em dash|\u2014/i,'Contains an em dash']].forEach(r=>{if(r[0].test(text))out.push(r[1])});if(text.trim().length<30)out.push('Prompt is too short to steer the agent');return out}
function promptsView(cid){
 const rep=S.user.role==='Rep';
 const c=cid?C(cid):C(UI.fil.prc||'C1');const P_=UI.pr=UI.pr||{};if(P_.cid!==c.id){P_.cid=c.id;P_.role='Writer';P_.v=null;P_.cmp=false}
 const role=P_.role;const vs=pver(c.id,role);const act_=vs.find(v=>v.status==='active')||vs[0];const view=vs.find(v=>v.v===P_.v)||act_;P_.v=view.v;
 const roles=ROLES.map(r=>{const a=pver(c.id,r).find(v=>v.status==='active');return`<button class="item ${r===role?'on':''}" data-a="prRole" data-k="${r}" style="width:100%;text-align:left;border:0;background:${r===role?'var(--mist)':'transparent'}"><div class="grow"><b style="font-weight:550">${r}</b><div class="small muted">${a?'Active v'+a.v:'No active version'}${a&&a.gold?', golden '+a.gold[1]:''}</div></div></button>`}).join('');
 const histRows=vs.map(v=>`<tr class="click" data-a="prVer" data-v="${v.v}"><td><b style="font-weight:550">v${v.v}</b> ${v.status==='active'?'<span class="pill live">Active</span>':v.status==='draft'?'<span class="pill draft">Draft</span>':'<span class="pill done">Archived</span>'}</td><td class="small">${esc(U(v.author).name)}</td><td class="small muted">${fDT(v.at)}</td><td class="small">${esc(v.note)}</td><td class="small">${v.gold?`${v.gold[1]} <span class="faint">${v.gold[0]}</span>`:'<span class="faint">Not run</span>'}</td><td class="small">${v.v>1||v.status==='active'?(vs.length>1?(S.jobs.filter(j=>j.cid===c.id&&j.pv===v.v&&roleOf(j)===role&&j.status==='done'&&!j.replay).length):0):S.jobs.filter(j=>j.cid===c.id&&j.pv===v.v&&roleOf(j)===role&&j.status==='done'&&!j.replay).length} runs</td></tr>`).join('');
 let editor='';
 if(P_.cmp&&vs.length>1){
  const other=vs.find(v=>v.v===(P_.cmpv||(view.v===act_.v?vs.find(x=>x.v!==act_.v).v:act_.v)))||vs[0];
  const d=diffLinesHtml(other.lines,view.lines);
  editor=`<div class="row" style="margin-bottom:10px"><b style="font-weight:550">Compare</b><select class="sel sm" style="width:auto" data-i="prcmp">${vs.filter(v=>v.v!==view.v).map(v=>`<option value="${v.v}" ${v.v===other.v?'selected':''}>v${v.v}</option>`).join('')}</select><span class="muted small">against v${view.v}</span><span class="right"></span><button class="btn sm" data-a="prCmp">Close compare</button></div><div class="grid g2"><div><div class="lbl small">v${other.v}</div><div class="pre diff" style="margin-top:6px">${d.a}</div></div><div><div class="lbl small">v${view.v}</div><div class="pre diff" style="margin-top:6px">${d.b}</div></div></div>`;
 }else{
  editor=`<textarea class="txt code" id="prText" rows="16" ${rep?'readonly':''} data-i="prEdit">${esc(view.lines.join('\n'))}</textarea><div id="prLint" class="small" style="margin-top:8px"></div>`;
 }
 return`<div class="pad col gap16">${cid?'':`<div class="filters"><select class="sel" data-i="prc">${S.camps.map(x=>`<option value="${x.id}" ${x.id===c.id?'selected':''}>${x.id} ${esc(x.name)}</option>`).join('')}</select></div>`}
 <div class="banner info" style="font-weight:450">${ic('info',16)}Edits here change only campaign ${c.id}, ${esc(c.name)}. Other campaigns keep their own prompts.${rep?' You have read access.':''}</div>
 <div class="split" style="grid-template-columns:240px minmax(0,1fr)"><div class="card tight" style="padding:8px">${roles}</div>
 <div class="col gap16"><div class="card"><div class="cardhead"><div><div class="h3">${role} prompt, v${view.v} ${view.status==='active'?'<span class="pill live">Active</span>':view.status==='draft'?'<span class="pill draft">Draft</span>':'<span class="pill done">Archived</span>'}</div><div class="small muted" style="margin-top:2px">${esc(view.note)} by ${esc(U(view.author).name)}, ${fDT(view.at)}</div></div><div class="row">${view.gold?`<span class="chip line">Golden set ${view.gold[1]}</span>`:''}<button class="btn sm" data-a="prGold">${ic('play',14)}Run golden set</button></div></div>
 ${editor}
 ${rep||P_.cmp?'':`<div class="row wrap" style="margin-top:14px"><button class="btn" data-a="prSave">Save as new version</button>${view.status!=='active'?`<button class="btn pri" data-a="prActivate" data-v="${view.v}">Activate v${view.v}</button>`:''}${vs.length>1?`<button class="btn" data-a="prCmp">${ic('branch',15)}Compare versions</button>`:''}${view.status==='active'&&vs.length>1?`<button class="btn" data-a="prRoll">Roll back</button>`:''}<button class="btn ghost" data-a="prCoach">${ic('spark',15)}Suggest an improvement</button></div>`}
 <div id="prCoachOut"></div></div>
 <div class="card"><div class="cardhead"><div class="h3">Version history</div></div><div class="tblwrap"><table class="tbl"><thead><tr><th>Version</th><th>Author</th><th>Date</th><th>Note</th><th>Golden set</th><th>Used in</th></tr></thead><tbody>${histRows}</tbody></table></div></div></div></div></div>`;
}
function pgPrompts(){return`${band({slim:true,crumbs:[['Workspace'],['Prompts and Harness']],title:'Prompts and Harness',sub:'Each role has its own versioned prompt. Activate a version and the next job uses it.'})}${promptsView(null)}`}
ACT.prRole=t=>{UI.pr.role=t.dataset.k;UI.pr.v=null;UI.pr.cmp=false;repaint()};
ACT.prVer=t=>{UI.pr.v=+t.dataset.v;UI.pr.cmp=false;repaint()};
ACT.prCmp=()=>{UI.pr.cmp=!UI.pr.cmp;UI.pr.cmpv=null;repaint()};





/* ---------- knowledge base ---------- */
function knowledgeView(cid){
 const c=cid?C(cid):C(UI.fil.kbc||'C1');const rep=S.user.role==='Rep';
 const docs=S.kb.docs.filter(d=>d.scope==='global'||d.scope===c.id);
 const kq=UI.kq||'';
 const rows=g=>docs.filter(d=>g?d.scope==='global':d.scope!=='global').map(d=>`<tr><td><b style="font-weight:550">${esc(d.name)}</b></td><td><span class="chip">${esc(d.type)}</span></td><td>${d.scope==='global'?'<span class="chip line">Global</span>':campChip(d.scope)}</td><td>${d.chunks.length}</td><td class="small muted">${fDT(d.at)}</td><td class="tar"><button class="btn xs" data-a="kbView" data-id="${d.id}">View chunks</button>${rep?'':`<button class="btn xs" data-a="kbRe" data-id="${d.id}">Re-ingest</button><button class="btn xs" data-a="kbDel" data-id="${d.id}">Delete</button>`}</td></tr>`).join('');
 const res=UI.kres?`<div class="col gap12" style="margin-top:14px">${UI.kres.length?UI.kres.map(r=>`<div class="card tight flat"><div class="row"><b style="font-weight:550">${esc(r.doc)}</b><span class="mono faint">${r.id}</span><span class="right"></span><span class="chip">score ${r.s.toFixed(2)}</span></div><div class="small muted" style="margin-top:6px">${esc(r.text)}</div></div>`).join(''):empty('No chunk matches','Nothing in the knowledge for this campaign answers that. The Writer would leave the claim out.')}</div>`:'';
 return`<div class="pad col gap16">${cid?'':`<div class="filters"><select class="sel" data-i="kbc">${S.camps.map(x=>`<option value="${x.id}" ${x.id===c.id?'selected':''}>${x.id} ${esc(x.name)}</option>`).join('')}</select><span class="muted small">Showing global knowledge plus ${esc(c.name)}</span>${rep?'':`<span class="right"></span><button class="btn pri" data-a="kbUp" data-c="${c.id}">${ic('plus',15)}Upload document</button>`}</div>`}
 ${cid&&!rep?`<div class="row"><span class="muted small">Global knowledge plus documents for ${esc(c.name)}.</span><span class="right"></span><button class="btn pri" data-a="kbUp" data-c="${c.id}">${ic('plus',15)}Upload document</button></div>`:''}
 <div class="card"><div class="cardhead"><div class="h3">Test search</div></div><div class="row"><input class="inp" id="kq" placeholder="Try: data residency, pricing, case study" value="${esc(kq)}"><button class="btn pri" data-a="kbSearch" data-c="${c.id}">${ic('search',15)}Search</button></div><div class="muted small" style="margin-top:8px">This is the search the Writer and Responder use. Scores rank keyword overlap in the demo.</div>${res}</div>
 <div class="card"><div class="cardhead"><div class="h3">Global documents</div></div><div class="tblwrap"><table class="tbl"><thead><tr><th>Document</th><th>Type</th><th>Scope</th><th>Chunks</th><th>Last ingested</th><th></th></tr></thead><tbody>${rows(true)}</tbody></table></div></div>
 <div class="card"><div class="cardhead"><div class="h3">${esc(c.name)} documents</div></div>${docs.some(d=>d.scope!=='global')?`<div class="tblwrap"><table class="tbl"><thead><tr><th>Document</th><th>Type</th><th>Scope</th><th>Chunks</th><th>Last ingested</th><th></th></tr></thead><tbody>${rows(false)}</tbody></table></div>`:empty('No campaign documents','Add a case study and an objection doc so the Writer has something to cite.',rep?'':`<br><button class="btn pri" data-a="kbUp" data-c="${c.id}">Upload document</button>`)}</div></div>`;
}
function pgKnowledge(){return`${band({slim:true,crumbs:[['Workspace'],['Knowledge Base']],title:'Knowledge Base',sub:'The only material agents may cite. Global documents apply everywhere. Campaign documents apply to one campaign.'})}${knowledgeView(null)}`}
ACT.kbView=t=>{const d=S.kb.docs.find(x=>x.id===t.dataset.id);openModal(`<div class="row"><h2>${esc(d.name)}</h2><span class="right"></span><button class="btn ghost sm" data-a="closeModal">${ic('x',16)}</button></div><div class="col gap12" style="margin-top:14px;max-height:420px;overflow:auto">${d.chunks.map(k=>`<div class="card tight flat"><div class="mono faint">${k}</div><div class="small" style="margin-top:4px">${esc(S.kb.chunks[k]?S.kb.chunks[k].text:'')}</div></div>`).join('')}</div>`,'lg')};




/* ---------- analytics ---------- */
function pgAnalytics(){
 const R=UI.fil.anr||'7d',since=R==='24h'?S.now-D:R==='3d'?S.now-3*D:R==='7d'?S.now-7*D:null;
 const cf=UI.fil.anc||'';const camps=S.camps.filter(c=>c.status!=='archived'&&(!cf||c.id===cf));
 const pc=x=>Math.round(x*100)+'%';
 const rows=camps.map(c=>{const s=cstats(c.id,since);const low=s.touches<20;const cell=v=>low?'<span class="faint small" title="Metrics appear after the first 20 touches">Under 20 touches</span>':v;
  return`<tr><td><div class="row">${campChip(c.id)}<b style="font-weight:550">${esc(c.name)}</b></div></td><td>${s.prospects}</td><td>${s.touches}</td><td>${s.contacted}</td><td>${cell(pc(s.replyRate))}</td><td>${cell(pc(s.posRate))}</td><td>${cell(pc(s.meetRate))}</td><td>${s.qualified?money(s.cpql):'-'}</td><td>${s.replies?money(s.cpc):'-'}</td></tr>`}).join('');
 const fun=camps.filter(c=>enrIn(c.id).length).map(c=>{const f=funnel(c.id);const mx=Math.max(1,f[0].n);return`<div class="card tight"><div class="row" style="margin-bottom:10px">${campChip(c.id)}<b style="font-weight:550">${esc(c.name)}</b></div>${stagebar(f)}</div>`}).join('');
 const byAg={};S.jobs.filter(j=>j.status==='done'&&!j.replay&&(!since||(j.end||j.at)>=since)&&(!cf||j.cid===cf)).forEach(j=>{byAg[j.agent]=(byAg[j.agent]||0)+(j.cost||0)});
 const tot=Object.values(byAg).reduce((a,b)=>a+b,0)||1,mxa=Math.max(0.0001,...Object.values(byAg));
 const cost=`<div class="stagebar" style="--w:150px">${AGENTS.map(a=>`<div class="r" style="grid-template-columns:110px 1fr 90px"><span>${a.k}</span><div class="bar"><i style="width:${100*(byAg[a.k]||0)/mxa}%"></i></div><span class="tar"><b style="font-weight:550">${money(byAg[a.k]||0)}</b> <span class="faint small">${Math.round(100*(byAg[a.k]||0)/tot)}%</span></span></div>`).join('')}</div>`;
 const gold=['C1','C2','C3'].flatMap(cid=>['Qualifier','Responder','Writer'].map(role=>{const vs=pver(cid,role).filter(v=>v.gold);if(vs.length<2)return'';const a=vs.find(v=>v.v===1),b=vs.find(v=>v.v===2);return`<tr><td>${campChip(cid)}</td><td>${role}</td><td>${a.gold[1]}</td><td><b style="font-weight:550">${b.gold[1]}</b></td><td class="small muted">${esc(b.gold[0])}</td></tr>`})).join('');
 const variants=S.camps.filter(c=>c.parent);
 const ab=variants.length?variants.map(v=>{const a=cstats(v.parent),b=cstats(v.id);return`<tr><td>${campChip(v.parent)} vs ${campChip(v.id)}</td><td>${pc(a.replyRate)}</td><td>${pc(b.replyRate)}</td><td>${a.touches}/${b.touches}</td><td class="small muted">${a.touches<20||b.touches<20?'Not enough data yet':'Read the difference with care'}</td></tr>`}).join(''):'';
 return`${band({slim:true,crumbs:[['Command Center','/overview'],['Analytics']],title:'Analytics',sub:'Compare campaigns on the same yardstick. Rates need 20 touches before they show.'})}<div class="pad col gap16">
 <div class="filters"><div class="seg">${[['24h','24 hours'],['3d','3 days'],['7d','7 days'],['all','All time']].map(x=>`<button class="${R===x[0]?'on':''}" data-a="anR" data-k="${x[0]}">${x[1]}</button>`).join('')}</div><select class="sel" data-i="anc"><option value="">All campaigns</option>${S.camps.map(c=>`<option value="${c.id}" ${cf===c.id?'selected':''}>${c.id} ${esc(c.name)}</option>`).join('')}</select><span class="muted small right">Demo data ${demoTag}</span></div>
 <div class="tblwrap"><table class="tbl"><thead><tr><th>Campaign</th><th>Prospects</th><th>Touches</th><th>Contacted</th><th>Reply rate</th><th>Positive rate</th><th>Meeting rate</th><th>Cost per qualified lead</th><th>Cost per conversation</th></tr></thead><tbody>${rows}</tbody></table></div>
 <div><div class="h3" style="margin-bottom:10px">Funnel by campaign</div><div class="grid g3">${fun||empty('No funnel yet','Add prospects to a campaign first.')}</div></div>
 <div class="grid g2"><div class="card"><div class="cardhead"><div class="h3">Model cost by agent</div><span class="muted small">${money(Object.values(byAg).reduce((a,b)=>a+b,0))} total</span></div>${cost}</div>
 <div class="card"><div class="cardhead"><div class="h3">Prompt versions on the golden set</div></div><div class="tblwrap"><table class="tbl"><thead><tr><th>Campaign</th><th>Role</th><th>v1</th><th>v2</th><th>Detail</th></tr></thead><tbody>${gold}</tbody></table></div></div></div>
 <div class="card"><div class="cardhead"><div class="h3">Variant comparison</div></div>${ab?`<div class="tblwrap"><table class="tbl"><thead><tr><th>Pair</th><th>Reply rate A</th><th>Reply rate B</th><th>Touches A/B</th><th>Read</th></tr></thead><tbody>${ab}</tbody></table></div>`:`<div class="muted">No variants yet. Duplicate a campaign as a variant, change one prompt, and compare here once both have 20 touches.</div><button class="btn sm" style="margin-top:12px" data-go="/campaigns">Open campaigns</button>`}</div></div>`;
}
ACT.anR=t=>{UI.fil.anr=t.dataset.k;repaint()};
/* ---------- settings ---------- */
function pgSettings(tab){
 const T=[{k:'integrations',l:'Integrations'},{k:'reps',l:'Reps'},{k:'suppression',l:'Suppression list',n:S.suppress.length},{k:'demo',l:'Demo tools'}];
 const tb=`<div class="tabs">${T.map(x=>`<a data-go="/settings/${x.k}" class="${tab===x.k?'on':''}">${x.l}${x.n!=null?`<span class="cnt">${x.n}</span>`:''}</a>`).join('')}</div>`;
 let body='';
 if(tab==='integrations'){
  const chMap={gmail:'email',linkedin:'linkedin',twilio:'sms',voice:'voice'};
  body=`<div class="pad"><div class="grid g2">${Object.entries(S.integ).map(([k,v])=>`<div class="card"><div class="cardhead"><div class="row"><b style="font-size:16px">${v.n}</b>${v.status!=='ok'?'<span class="pill bad">'+ic('alert',12)+'Error</span>':v.canLive?'<span class="pill live"><i class="dot live"></i>Connected</span>':'<span class="pill draft">Not connected</span>'}${v.paused?'<span class="pill paused">Paused</span>':''}</div>${chMap[k]?`<div class="row"><span class="small muted">Enabled</span>${sw(!v.paused,'integSw','data-k="'+k+'"')}</div>`:''}</div><div class="muted small">${v.d}</div>${v.err?`<div class="banner bad" style="margin-top:12px;font-weight:450;align-items:flex-start">${ic('alert',16)}<span>${esc(v.err)}</span></div>`:''}<div class="row wrap" style="margin-top:14px"><span class="small faint">Last check ${rel(v.last)}</span><span class="right"></span>${v.canLive?`<div class="seg"><button class="${v.mode==='live'?'on':''}" data-a="integMode" data-k="${k}" data-m="live">Live</button><button class="${v.mode==='sandbox'?'on':''}" data-a="integMode" data-k="${k}" data-m="sandbox">Sandbox</button></div>`:'<span class="tag sbx">SANDBOX ONLY</span>'}<button class="btn sm" data-a="integTest" data-k="${k}">Test connection</button></div></div>`).join('')}</div></div>`;
 }else if(tab==='reps'){
   body=`<div class="pad"><div class="row" style="margin-bottom:14px"><span class="muted">Reps receive escalations and own the meetings the agents book. Admins and managers add reps, managers and other admins.</span><span class="right"></span>${['Admin','Manager'].includes(S.user.role)?`<button class="btn pri" data-a="repAdd">${ic('plus',15)}Add user</button>`:''}</div><div class="tblwrap"><table class="tbl"><thead><tr><th>Person</th><th>Role</th><th>Hours</th><th>Daily limit</th><th>Channels</th><th>Campaigns</th><th>Status</th><th></th></tr></thead><tbody>${S.users.map(u=>`<tr><td><div class="row">${av(u.name,'',u.active)}<div><b style="font-weight:550">${esc(u.name)}</b><div class="small muted">${esc(u.title)}${u.label?', '+u.label:''}</div></div></div></td><td>${u.role}</td><td class="small">${u.hours} ${u.tz}</td><td>${u.role==='Rep'?`<input class="inp sm" type="number" min="0" style="width:80px" data-i="repLim" data-id="${u.id}" value="${u.limit}">`:'-'}</td><td class="small">${u.channels.map(c=>CH[c].n).join(', ')}</td><td>${S.camps.filter(c=>c.reps.includes(u.id)).map(c=>campChip(c.id)).join('')||'<span class="faint">None</span>'}</td><td>${u.active?'<span class="pill live">Active</span>':'<span class="pill done">Offboarded</span>'}</td><td class="tar"><span class="row gap8" style="justify-content:flex-end">${u.role==='Rep'&&u.active?`<button class="btn xs" data-a="repOff" data-id="${u.id}">Offboard</button>`:''}${u.role==='Rep'?`<button class="btn xs" data-a="repDel" data-id="${u.id}">${ic('trash',13)}Delete</button>`:''}</span></td></tr>`).join('')}</tbody></table></div></div>`;
 }else if(tab==='suppression'){
  body=`<div class="pad col gap16"><div class="card"><div class="cardhead"><div class="h3">Add to suppression list</div></div><div class="row wrap"><select class="sel" id="sup1" style="width:auto"><option value="email">Email</option><option value="domain">Domain</option><option value="phone">Phone</option></select><input class="inp" id="sup2" style="max-width:280px" placeholder="name@example.com"><input class="inp" id="sup3" style="max-width:280px" placeholder="Reason"><button class="btn pri" data-a="supAdd">Add</button></div><div class="muted small" style="margin-top:8px">The Guardian blocks every send to a suppressed contact, in every campaign, on every channel.</div></div>
  <div class="tblwrap"><table class="tbl"><thead><tr><th>Type</th><th>Value</th><th>Reason</th><th>Added by</th><th>Date</th><th></th></tr></thead><tbody>${S.suppress.map(x=>`<tr><td><span class="chip">${x.kind}</span></td><td>${esc(x.value)}</td><td class="small">${esc(x.reason)}</td><td class="small">${esc(x.by)}</td><td class="small muted">${fD(x.at)}</td><td class="tar"><button class="btn xs" data-a="supDel" data-id="${x.id}">Remove</button></td></tr>`).join('')||`<tr><td colspan="6">${empty('Nobody is suppressed','Opt-outs land here.')}</td></tr>`}</tbody></table></div></div>`;
 }else{
  body=`<div class="pad col gap16"><div class="banner info" style="font-weight:450">${ic('info',16)}These tools exist only in the demo. They let you run a whole week of outreach in a few minutes.</div>
  <div class="grid g2"><div class="card"><div class="h3">Advance the demo clock</div><p class="muted small" style="margin:6px 0 14px">Jumps forward, then runs everything that came due. Follow-ups, wake dates and held frequency caps fire.</p><div class="row wrap"><button class="btn" data-a="adv" data-h="1">+1 hour</button><button class="btn" data-a="adv" data-h="6">+6 hours</button><button class="btn pri" data-a="adv" data-h="24">+24 hours</button></div></div>
  <div class="card"><div class="h3">Simulate discovery</div><p class="muted small" style="margin:6px 0 14px">Adds five new prospects to a campaign.</p><button class="btn" data-a="discoverAny">Choose a campaign</button></div>
  <div class="card"><div class="h3">Play a scripted call outcome</div><p class="muted small" style="margin:6px 0 14px">Runs the voice post-call path with a scripted transcript, labelled SANDBOX. Use it when telephony is unavailable.</p><button class="btn" data-a="playCall">Choose a prospect</button></div>
  <div class="card"><div class="h3">Reset demo data</div><p class="muted small" style="margin:6px 0 14px">Rebuilds the seeded workspace. Every change you made goes away.</p><button class="btn dan" data-a="reset">Reset data</button></div></div></div>`;
 }
 return`${band({slim:true,crumbs:[['Workspace'],['Settings']],title:'Settings',sub:'Integrations, reps, the suppression list and demo tools.'})}${tb}${body}`;
}









/* ---------- search, events, boot ---------- */
function gsearch(q){
 q=q.trim().toLowerCase();const box=$('#sres');if(!box)return;if(!q){box.innerHTML='';return}
 const ps=Object.values(S.people).filter(p=>(p.name+' '+p.company).toLowerCase().includes(q)).slice(0,6);
 const cs=S.camps.filter(c=>(c.name+' '+c.id).toLowerCase().includes(q)).slice(0,3);
 const rows=ps.map(p=>`<a data-go="/prospects/${p.id}">${av(p.name,'sm')}<span><b style="font-weight:550">${esc(p.name)}</b> <span class="muted small">${esc(p.company)}</span></span></a>`).concat(cs.map(c=>`<a data-go="/campaigns/${c.id}/overview">${campChip(c.id)}<span>${esc(c.name)}</span></a>`));
 box.innerHTML=`<div class="sresults">${rows.join('')||'<div class="muted small" style="padding:12px">No prospect, company or campaign matches.</div>'}</div>`;
}



function editing(){const a=document.activeElement;return a&&['INPUT','TEXTAREA','SELECT'].includes(a.tagName)&&$('#view')&&$('#view').contains(a)}
function afterPaint(parts){
 if(UI.refocus){const el=$('[data-i="'+UI.refocus+'"]');if(el){el.focus();try{const n=el.value.length;el.setSelectionRange(n,n)}catch(e){}}UI.refocus=null}
 const prEd=$('#prText');if(prEd&&!prEd.readOnly){prEd.oninput=()=>{const l=lintPrompt(prEd.value);$('#prLint').innerHTML=l.map(x=>`<span class="pill bad" style="margin-right:6px">${esc(x)}</span>`).join('')}}
}
function updateBadges(){const n=needsCount();const nb=$('#nb');if(nb){nb.textContent=n;nb.classList.toggle('hot',!!n)}const bn=$('#bn');if(bn){bn.textContent=n;bn.hidden=!n}const ck=$('#clk');if(ck)ck.textContent=fDT(S.now)}




ACT.logout=()=>{S.user=null;UI.menu=null;paint()};
ACT.sideToggle=()=>{$('#side').classList.toggle('open')};



document.addEventListener('click',e=>{
 if(UI.menu&&!e.target.closest('.menuwrap')){UI.menu=null;repaint()}
 const gs=$('#sres');if(gs&&!e.target.closest('.search'))gs.innerHTML='';
 const a=e.target.closest('[data-a]');
 if(a&&!a.disabled){const f=ACT[a.dataset.a];if(f){e.preventDefault();f(a,e)}return}
 if(e.target.closest('[data-stop]'))return;
 const g=e.target.closest('[data-go]');
 if(g){e.preventDefault();UI.q='';go(g.dataset.go);const s=$('#side');if(s)s.classList.remove('open')}
});
const GEN_I=['campq','pq','pc','ps','pscore','pch','pconf','actc','acts','swc','prc','kbc','anc'];
const TXT_I=['campq','pq'];
function onField(e){
 const el=e.target;const i=el.dataset&&el.dataset.i;if(!i){if(el.id==='gs')gsearch(el.value);return}
 const isInput=e.type==='input';
 if(GEN_I.includes(i)){if(isInput&&!TXT_I.includes(i))return;UI.fil[i]=el.type==='checkbox'?el.checked:el.value;if(i==='campq')UI.fil.campq=el.value;if(i==='prc')UI.pr=null;if(TXT_I.includes(i))UI.refocus=i;repaint();return}
 if(i==='feedCamp'&&!isInput){UI.fil.feed=el.value;$('#feedbox').innerHTML=feedList(20,el.value);return}
 if(i==='cf'){UI.cf[el.dataset.f]=el.value;refreshCk();return}
 if(i==='cfSel'&&!isInput){UI.cf[el.dataset.f]=el.value==='1';refreshCk();return}
 if(i==='cfTpl'&&!isInput){if(el.value){cfFill(UI.cf,el.value);repaint()}return}
 if((i==='cfDoc'||i==='cfRep')&&!isInput){const k=i==='cfDoc'?'docs':'reps';const a=UI.cf[k];const id=el.dataset.id;const ix=a.indexOf(id);if(el.checked&&ix<0)a.push(id);if(!el.checked&&ix>=0)a.splice(ix,1);refreshCk();return}
 if(i==='cfg'&&!isInput){const{c,b}=cfgPatch(el);run(()=>api.patch('/campaigns/'+c.id,b),{ok:'Saved as a new campaign version. It applies to the next job.'});return}
 if(i==='cfgRep'&&!isInput){const c=C(el.dataset.id),u=el.dataset.u;const reps=c.reps.filter(x=>x!==u);if(el.checked)reps.push(u);run(()=>api.patch('/campaigns/'+c.id,{rep_ids:reps}),{ok:'Reps updated.'});return}
 if(i==='campSw'&&!isInput){if(el.value)go('/campaigns/'+el.value+'/overview');return}
 if(i==='prcmp'&&!isInput){UI.pr.cmpv=+el.value;repaint();return}
 if(i==='repLim'&&!isInput){run(()=>api.patch('/reps/'+el.dataset.id,{rep_limit:+el.value}),{ok:'Daily limit saved.'});return}
}
document.addEventListener('input',onField);document.addEventListener('change',onField);
document.addEventListener('toggle',e=>{const d=e.target;if(d.dataset&&d.dataset.sec){UI.open=UI.open||{};UI.open[d.dataset.sec]=d.open}},true);
document.addEventListener('keydown',e=>{
 if(e.key==='Escape'){if($('#modal'))closeModal();else if($('#drawer'))closeDrawer();else if(UI.menu){UI.menu=null;repaint()}}
 if(e.key==='Enter'){const t=e.target;
  if(t.id==='lpw'||t.id==='lem'){ACT.login();return}
  if(t.id==='gs'){const a=$('#sres a');if(a)a.click();return}
  if(t.id==='kq'){const b=$('[data-a=kbSearch]');if(b)b.click();return}
  if(t.matches&&t.matches('[role=link]')){t.click()}}
});
