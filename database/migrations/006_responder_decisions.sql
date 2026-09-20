-- A hosted Responder agent submits its decision through the set_classification MCP tool. The worker reads it from here.
create table responder_decisions (
  id bigserial primary key,
  enrollment_id text not null references enrollments(id) on delete cascade,
  decision jsonb not null,
  saved_at timestamptz not null default now()
);
create index responder_decisions_lookup on responder_decisions (enrollment_id, saved_at desc);
alter table responder_decisions enable row level security;
