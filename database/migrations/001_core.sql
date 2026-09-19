create extension if not exists vector;

create sequence if not exists id_seq start 10000;

create table users (
  id text primary key,
  name text not null,
  role text not null check (role in ('Admin', 'Manager', 'Rep')),
  email text not null unique,
  password_hash text not null,
  title text not null default '',
  rep_limit int not null default 0,
  hours text not null default '09:00 to 18:00',
  tz text not null default 'IST',
  channels text[] not null default '{}',
  active boolean not null default true,
  label text not null default ''
);

create table global_settings (
  id int primary key default 1 check (id = 1),
  kill_switch boolean not null default false,
  kill_at timestamptz,
  kill_by text,
  frequency_window_hours int not null default 48,
  demo_clock_offset_hours double precision not null default 0
);
insert into global_settings (id) values (1);

create table integrations (
  key text primary key,
  name text not null,
  description text not null,
  mode text not null default 'sandbox' check (mode in ('live', 'sandbox')),
  status text not null default 'ok',
  last_check timestamptz,
  err text,
  can_live boolean not null default true,
  paused boolean not null default false
);

create table campaigns (
  id text primary key,
  name text not null,
  description text not null default '',
  owner_id text not null references users(id),
  status text not null default 'draft' check (status in ('draft', 'live', 'paused', 'completed', 'archived')),
  objective text not null default '',
  icp text not null default '',
  personas text not null default '',
  geo text not null default '',
  signals text not null default '',
  seq_order text not null default '',
  tone text not null default '',
  words int not null default 90,
  approval_text text not null default '',
  roles text[] not null default '{}',
  geo_list text[] not null default '{}',
  exclusions text[] not null default '{}',
  refs text not null default '',
  thr int not null default 70,
  appr jsonb not null default '{"first": false, "voice": true, "reply": true}',
  daily_send_cap int not null default 30,
  priority int not null default 50,
  ch_limit jsonb not null default '{"email": 40, "linkedin": 20, "sms": 10, "voice": 5}',
  version int not null default 1,
  parent_id text references campaigns(id),
  paused_by text,
  paused_at timestamptz,
  paused_held int not null default 0,
  created_at timestamptz not null default now(),
  last_activity timestamptz,
  dry_ok boolean not null default false,
  tpl text
);

create table campaign_versions (
  id bigserial primary key,
  campaign_id text not null references campaigns(id),
  version int not null,
  config jsonb not null,
  changed_by text,
  changed_at timestamptz not null default now(),
  note text not null default ''
);

create table campaign_agents (
  campaign_id text not null references campaigns(id) on delete cascade,
  agent_key text not null,
  enabled boolean not null default true,
  provider text,
  model text,
  thresholds jsonb not null default '{}',
  tools jsonb not null default '[]',
  escalation_rules jsonb not null default '{}',
  primary key (campaign_id, agent_key)
);

create table channel_settings (
  campaign_id text not null references campaigns(id) on delete cascade,
  channel text not null check (channel in ('email', 'linkedin', 'sms', 'voice')),
  enabled boolean not null default false,
  daily_limit int not null default 0,
  health text not null default 'ok',
  primary key (campaign_id, channel)
);

create table rep_assignments (
  rep_id text not null references users(id),
  campaign_id text not null references campaigns(id) on delete cascade,
  daily_limit_override int,
  active boolean not null default true,
  primary key (rep_id, campaign_id)
);

create table prompt_versions (
  id text primary key,
  campaign_id text not null references campaigns(id) on delete cascade,
  agent_key text not null,
  version int not null,
  status text not null check (status in ('draft', 'active', 'archived')),
  author_id text references users(id),
  created_at timestamptz not null default now(),
  change_note text not null default '',
  lines jsonb not null,
  parent_version int,
  gold jsonb,
  unique (campaign_id, agent_key, version)
);
create unique index prompt_one_active on prompt_versions (campaign_id, agent_key) where status = 'active';

create table companies (
  id text primary key,
  name text not null,
  domain text not null,
  industry text not null default '',
  staff int not null default 0,
  stage text not null default '',
  city text not null default ''
);

create table prospects (
  id text primary key,
  company_id text not null references companies(id),
  full_name text not null,
  first_name text not null,
  title text not null,
  email text not null,
  phone text not null default '',
  linkedin_url text not null default '',
  region text not null default 'US',
  timezone text not null default 'PT',
  facts jsonb not null default '[]',
  rich jsonb not null default '[]',
  researched boolean not null default false,
  bio text not null default '',
  thin boolean not null default false,
  is_empty boolean not null default false,
  rej jsonb not null default '{}',
  is_seed boolean not null default false
);
create unique index prospects_email_uq on prospects (lower(email));

create table enrollments (
  id text primary key,
  campaign_id text not null references campaigns(id),
  prospect_id text not null references prospects(id),
  state text not null default 'new',
  score int,
  crit jsonb,
  plan jsonb not null default '[]',
  rep_id text references users(id),
  reject text,
  review_note text,
  defer_note text,
  hold jsonb,
  plan_hist jsonb not null default '[]',
  meeting jsonb,
  slots jsonb,
  wake timestamptz,
  warm boolean not null default false,
  hot_call boolean not null default false,
  first_due timestamptz,
  last_touch timestamptz,
  note text,
  created_at timestamptz not null default now(),
  is_seed boolean not null default false,
  unique (campaign_id, prospect_id)
);
create index enrollments_campaign_state on enrollments (campaign_id, state);
