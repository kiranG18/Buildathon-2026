/* API client: token handling, the call helper, and hydrate(), which keeps S in sync with GET /state. */
let TOKEN=null;
try{TOKEN=sessionStorage.getItem('cadence.token')}catch(e){TOKEN=null}
const NET={err:null,last:null,retryAt:0};
let LASTSIG=null,PUB=[];

async function call(method,path,body,opts){
 opts=opts||{};
 let res;
 try{
  res=await fetch(path,{method,headers:Object.assign({'Content-Type':'application/json'},TOKEN?{Authorization:'Bearer '+TOKEN}:{}),body:body===undefined||body===null?undefined:JSON.stringify(body)});
 }catch(e){
  NET.err='network';NET.retryAt=Date.now()+5000;
  throw Object.assign(new Error('Cannot reach the server. Retrying in 5 seconds.'),{status:0,code:'network'});
 }
 if(NET.err==='network'){NET.err=null}
 let data={};
 try{data=await res.json()}catch(e){data={}}
 if(!res.ok){
  const err=data.error||{code:'error',message:'The request failed'};
  if(res.status===401&&TOKEN&&!opts.keepSession){signOut();}
  throw Object.assign(new Error(err.message),{status:res.status,code:err.code,detail:err});
 }
 return data;
}
const api={get:p=>call('GET',p),post:(p,b)=>call('POST',p,b||{}),put:(p,b)=>call('PUT',p,b||{}),patch:(p,b)=>call('PATCH',p,b||{}),del:p=>call('DELETE',p)};

function setToken(t){TOKEN=t;try{t?sessionStorage.setItem('cadence.token',t):sessionStorage.removeItem('cadence.token')}catch(e){}}
function signOut(){setToken(null);S=null;LASTSIG=null;UI.menu=null;UI.cf=null;UI.sel={};UI.fil={}}

function applyState(st){
 const prev=S?new Set(S.acts.map(a=>a.id)):null;
 st.enrById=Object.fromEntries(st.enr.map(e=>[e.id,e]));
 st.newActs=prev?st.acts.filter(a=>!prev.has(a.id)).map(a=>a.id):[];
 st.wall=Date.now();
 st.qh=S&&S.qh?S.qh:{};
 S=st;
 sampleQueue();
}
function sampleQueue(){
 S.camps.forEach(c=>{const a=S.qh[c.id]=S.qh[c.id]||[];a.push(S.jobs.filter(j=>j.cid===c.id&&j.status==='queued'&&jobState(j)!=='held').length);if(a.length>40)a.shift()});
}

/* Reads the cheap signature every poll and the full state only when something changed. Returns true when S changed. */
async function hydrate(force){
 if(!TOKEN)return false;
 try{
  const sg=await call('GET','/state/sig',null,{keepSession:false});
  NET.last=Date.now();
  if(!force&&S&&sg.sig===LASTSIG){S.now=sg.now;S.wall=Date.now();return false}
  const st=await call('GET','/state');
  applyState(st);LASTSIG=sg.sig;
  return true;
 }catch(e){
  if(e.status===0){NET.err='network'}
  return false;
 }
}

async function loadPublic(){
 try{PUB=await call('GET','/public/campaigns')}catch(e){PUB=[]}
}
