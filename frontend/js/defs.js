/* Static definitions shared by every screen. */
const COLORS={C1:'c1',C2:'c2',C3:'c3',C4:'c4'};
const CH={email:{n:'Email',i:'mail'},linkedin:{n:'LinkedIn',i:'linkedin'},sms:{n:'SMS',i:'sms'},voice:{n:'Voice',i:'phone'}};
const AGENTS=[
 {k:'Researcher',model:'DronaHQ agent, web search + enrichment',host:'DronaHQ',cost:.012,dur:4.1,d:'Finds and sources facts about the prospect'},
 {k:'Qualifier',model:'claude-haiku-4-5',host:'Direct',cost:.004,dur:1.2,d:'Scores fit against the campaign ICP'},
 {k:'Sequencer',model:'claude-sonnet-5',host:'Direct',cost:.018,dur:2.4,d:'Plans channel, timing and next step'},
 {k:'Writer',model:'claude-sonnet-5',host:'Direct',cost:.022,dur:3.1,d:'Drafts grounded messages on every channel'},
 {k:'Responder',model:'DronaHQ agent, MCP tools',host:'DronaHQ',cost:.015,dur:2.9,d:'Classifies replies and answers, books or escalates'},
 {k:'Caller',model:'DronaHQ Voice agent',host:'DronaHQ',cost:.11,dur:74,d:'Places and summarises voice calls'}
];
const AG=Object.fromEntries(AGENTS.map(a=>[a.k,a]));
const ROLES=['System','Qualifier','Researcher','Strategy','Follow-up','Writer','Responder','Caller'];
const STATE={
 new:{l:'Discovered',st:0,pill:'done',ic:'search'},researched:{l:'Researched',st:1,pill:'done',ic:'search'},rejected:{l:'Rejected',st:1,pill:'bad',ic:'x'},
 borderline:{l:'Needs review',st:1,pill:'warn',ic:'eye'},qualified:{l:'Qualified',st:2,pill:'info',ic:'target'},
 awaiting_approval:{l:'Draft awaiting approval',st:2,pill:'warn',ic:'edit'},awaiting_voice:{l:'Call awaiting approval',st:2,pill:'warn',ic:'phone'},
 deferred:{l:'Deferred by conflict',st:2,pill:'warn',ic:'shield'},contacted:{l:'Contacted',st:3,pill:'done',ic:'send'},
 replied_pos:{l:'Replied, positive',st:4,pill:'ok',ic:'msg'},replied_obj:{l:'Replied, objection',st:4,pill:'info',ic:'msg'},replied_notnow:{l:'Replied, not now',st:4,pill:'done',ic:'clock'},
 escalated:{l:'Escalated to rep',st:4,pill:'warn',ic:'handoff'},opted_out:{l:'Opted out',st:4,pill:'bad',ic:'stop'},meeting:{l:'Meeting booked',st:5,pill:'ok',ic:'calendar'},stopped:{l:'Stopped',st:1,pill:'bad',ic:'stop'}
};
const STAGES=['Discovered','Researched','Qualified','Contacted','Engaged','Meeting'];
const spill=s=>{const m=STATE[s]||STATE.new;const cls=m.pill==='ok'?'live':m.pill;return `<span class="pill ${cls}">${ic(m.ic,13)}${m.l}</span>`};
const ESC={pricing_negotiation:'Pricing negotiation',security_questionnaire:'Security questionnaire',legal_terms:'Legal terms',human_request:'Asked for a human',hostile_tone:'Hostile tone',knowledge_gap:'Knowledge gap',agent_failure:'Agent failure'};
