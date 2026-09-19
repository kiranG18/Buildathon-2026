create index if not exists conflicts_open on conflicts (status);
create index if not exists escalations_open on escalations (status);
create index if not exists jobs_status on jobs (status, run_at);
create index if not exists calls_enrollment on calls (enrollment_id);
create index if not exists meetings_campaign on meetings (campaign_id);
