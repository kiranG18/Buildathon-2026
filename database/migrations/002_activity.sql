create table jobs (
  id text primary key,
  campaign_id text not null references campaigns(id),
  enrollment_id text references enrollments(id),
  prospect_id text references prospects(id),
  agent text not null,
  step text not null,
  status text not null default 'queued' check (status in ('queued', 'running', 'done', 'failed', 'cancelled')),
  run_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  ended_at timestamptz,
  attempts int not null default 0,
  step_no int,
  payload jsonb,
  err text,
  msg_id text,
  is_replay boolean not null default false,
  is_seed boolean not null default false
);
create index jobs_claim on jobs (campaign_id, status, run_at);
create index jobs_enrollment on jobs (enrollment_id);

create table agent_runs (
  id text primary key,
  job_id text references jobs(id) on delete cascade,
  campaign_id text not null references campaigns(id),
  enrollment_id text,
  agent_key text not null,
  role text not null,
  provider text not null default 'direct',
  model text not null default '',
  prompt_version int,
  campaign_version int,
  retrieved_chunk_ids text[] not null default '{}',
  summary text not null default '',
  trace jsonb not null default '{}',
  input_snapshot jsonb,
  status text not null default 'done',
  tokens_in int not null default 0,
  tokens_out int not null default 0,
  cost_usd double precision not null default 0,
  latency_s double precision not null default 0,
  error text,
  is_replay boolean not null default false,
  is_seed boolean not null default false,
  created_at timestamptz not null default now()
);
create index agent_runs_campaign on agent_runs (campaign_id, created_at desc);
create index agent_runs_job on agent_runs (job_id);

create table messages (
  id text primary key,
  enrollment_id text not null references enrollments(id),
  prospect_id text not null references prospects(id),
  campaign_id text not null references campaigns(id),
  channel text not null,
  direction text not null check (direction in ('in', 'out')),
  body text not null,
  segs jsonb,
  created_at timestamptz not null default now(),
  mode text not null default 'sandbox',
  status text not null default 'sent',
  is_seed boolean not null default false,
  subject text,
  run_id text,
  kind text,
  step_no int,
  prompt_version int,
  approved_by text,
  classification text,
  rule text,
  sub text,
  is_reply boolean not null default false,
  is_ack boolean not null default false,
  human boolean not null default false,
  by_name text,
  edited boolean not null default false,
  idempotency_key text unique,
  gate_decision text,
  external_id text,
  rfc_message_id text
);
create index messages_enrollment on messages (enrollment_id, created_at);
create index messages_prospect on messages (prospect_id, created_at);
create index messages_campaign on messages (campaign_id, created_at);

create table activity (
  seq bigserial primary key,
  id text not null unique,
  ts timestamptz not null default now(),
  enrollment_id text,
  prospect_id text,
  campaign_id text,
  kind text not null,
  text text not null,
  agent text,
  run_id text,
  msg_id text,
  mode text,
  quiet boolean not null default false,
  prompt_version_id text,
  reason_code text
);
create index activity_campaign_ts on activity (campaign_id, ts desc);
create index activity_ts on activity (ts desc);

create table approvals (
  id text primary key,
  kind text not null check (kind in ('borderline', 'first_touch', 'voice', 'reply', 'conflict', 'prompt_change')),
  campaign_id text not null references campaigns(id),
  enrollment_id text references enrollments(id),
  created_at timestamptz not null default now(),
  status text not null default 'open' check (status in ('open', 'approved', 'rejected')),
  run_id text,
  msg_id text,
  step_no int,
  blocked boolean not null default false,
  decided_by text,
  decided_at timestamptz,
  reason text,
  payload jsonb
);
create index approvals_open on approvals (status, campaign_id);

create table escalations (
  id text primary key,
  enrollment_id text not null references enrollments(id),
  campaign_id text not null references campaigns(id),
  reason_code text not null,
  rep_id text references users(id),
  created_at timestamptz not null default now(),
  status text not null default 'open',
  msg_id text,
  suggested text not null default '',
  summary text not null default '',
  rule text not null default '',
  severity text not null default 'normal',
  created_by_agent text not null default 'Responder',
  resolved_by text,
  resolved_at timestamptz
);

create table meetings (
  id text primary key,
  enrollment_id text not null references enrollments(id),
  campaign_id text not null references campaigns(id),
  prospect_id text not null references prospects(id),
  slot_at timestamptz not null,
  rep_id text references users(id),
  label text not null,
  source text not null default 'agent',
  status text not null default 'booked',
  link text
);

create table calls (
  id text primary key,
  enrollment_id text not null references enrollments(id),
  prospect_id text not null references prospects(id),
  at timestamptz not null,
  dur text not null default '00:00',
  disposition text not null,
  mode text not null default 'sandbox',
  run_id text,
  transcript jsonb not null default '[]',
  summary text not null default '',
  recording_url text,
  objections jsonb not null default '[]',
  structured jsonb not null default '{}'
);

create table contact_claims (
  id bigserial primary key,
  prospect_id text not null references prospects(id),
  campaign_id text not null references campaigns(id),
  status text not null default 'active' check (status in ('active', 'released', 'lost')),
  priority int not null default 50,
  claimed_at timestamptz not null default now(),
  expires_at timestamptz
);
create unique index claims_one_active on contact_claims (prospect_id) where status = 'active';

create table conflicts (
  id text primary key,
  prospect_id text not null references prospects(id),
  campaign_ids text[] not null,
  rule text not null,
  winner text,
  status text not null default 'open',
  code text not null,
  decision text not null,
  created_at timestamptz not null default now(),
  resolved_by text
);

create table suppression_list (
  id text primary key,
  kind text not null check (kind in ('email', 'domain', 'phone')),
  value text not null,
  reason text not null,
  added_by text not null,
  created_at timestamptz not null default now(),
  scope text not null default 'global',
  campaign_id text references campaigns(id),
  unique (kind, value)
);
