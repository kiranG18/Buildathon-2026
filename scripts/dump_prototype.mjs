// Runs the prototype's own seed driver headlessly and writes seed/prototype_state.json.
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const html = fs.readFileSync(path.join(root, 'frontend/prototype/cadence-prototype.html'), 'utf8');
const m = html.match(/<script>([\s\S]*)<\/script>/);
let js = m[1].replace(/if\(document\.readyState==='loading'\)[^\n]*\n?$/m, '');
js += `\n;globalThis.__dump=()=>{seedAll();S.seeding=false;S.now=T0;return {S,POOL,RESERVE,T0,KTEXT,KDOCS,CRIT,SEQ,REASON,REJECTS,HERO_FACTS}};`;
const noop = () => {};
const ctx = { console, setInterval: noop, setTimeout: noop, clearTimeout: noop, location: { hash: '' }, Date, Math, JSON, Uint16Array,
  window: { addEventListener: noop }, document: { addEventListener: noop, readyState: 'complete', querySelector: () => null, querySelectorAll: () => [] } };
vm.createContext(ctx);
vm.runInContext(js, ctx);
const out = ctx.__dump();
const S = out.S;
delete S.newActs; delete S.wall; delete S.seeding; delete S.user; delete S.enrById;
fs.writeFileSync(path.join(root, 'seed/prototype_state.json'), JSON.stringify(out));
const { POOL, RESERVE, CRIT, SEQ, REASON, REJECTS, HERO_FACTS } = out;
fs.writeFileSync(path.join(root, 'seed/static.json'), JSON.stringify({ POOL, RESERVE, CRIT, SEQ, REASON, REJECTS, HERO_FACTS }));
const c = (k) => Array.isArray(S[k]) ? S[k].length : Object.keys(S[k]).length;
console.log(Object.fromEntries(['camps','users','people','enr','msgs','acts','jobs','approvals','escal','conflicts','meetings','calls','claims','suppress','prompts'].map(k=>[k,c(k)])));
