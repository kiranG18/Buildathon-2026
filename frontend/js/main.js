/* Boot, polling loop and the field/event handlers that were not extracted with the screens. */
const POLL_MS=3000;

function updateClock(){
 if(!S)return;
 const n=Date.now();S.now+=n-S.wall;S.wall=n;
 const ck=$('#clk');if(ck)ck.textContent=fDT(S.now);
}

async function poll(){
 if(!TOKEN||!S)return;
 const changed=await hydrate(false);
 updateBadges();
 if(NET.err!==UI.netShown){UI.netShown=NET.err;repaint()}
 const parts=UI.path.split('?')[0].split('/').filter(Boolean);
 const live=parts[0]==='overview'||parts[0]==='activity'||(parts[0]==='campaigns'&&(!parts[1]||['overview','activity'].includes(parts[2])));
 if(changed&&live&&!$('#modal')&&!$('#drawer')&&!editing()&&!UI.menu)repaint();
 S.newActs=[];
}

function boot(){
 UI.path=(location.hash||'#/overview').slice(1)||'/overview';
 setInterval(poll,POLL_MS);
 setInterval(updateClock,1000);
 if(!TOKEN){loadPublic().then(paint);paint();return}
 rootLoading();
 hydrate(true).then(()=>{if(S)paint();else{signOut();loadPublic().then(paint)}});
}
function rootLoading(){
 $('#root').innerHTML=`<div class="app"><aside class="side"><div class="brand"><i>${ic('route',16).replace('currentColor','#f6f7ee')}</i>Cadence</div><div class="col gap12" style="padding:0 10px">${'<div class="skel" style="height:34px"></div>'.repeat(8)}</div></aside><main class="main"><div class="band"><div class="skel" style="height:34px;width:320px"></div><div class="skel" style="height:18px;width:480px;margin-top:12px"></div></div><div class="pad"><div class="kpirow">${'<div class="skel" style="height:78px"></div>'.repeat(6)}</div></div></main></div>`;
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
