create index if not exists conflicts_open on conflicts (status);
create index if not exists escalations_open on escalations (status);
create index if not exists jobs_status on jobs (status, run_at);
create index if not exists calls_enrollment on calls (enrollment_id);
create index if not exists meetings_campaign on meetings (campaign_id);

create table research_callbacks (
  enrollment_id text not null references enrollments(id) on delete cascade,
  run_id text not null,
  facts_saved int not null default 0,
  saved_at timestamptz not null default now(),
  primary key (enrollment_id, run_id)
);
