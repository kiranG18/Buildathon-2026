create table knowledge_documents (
  id text primary key,
  name text not null,
  doc_type text not null,
  scope text not null,
  campaign_id text references campaigns(id) on delete cascade,
  metadata jsonb not null default '{}',
  source_path text,
  content_hash text,
  ingested_at timestamptz not null default now()
);

create table knowledge_chunks (
  id text primary key,
  document_id text not null references knowledge_documents(id) on delete cascade,
  campaign_id text,
  scope text not null,
  doc_type text not null,
  tags text[] not null default '{}',
  content text not null,
  embedding vector(1536),
  tsv tsvector generated always as (to_tsvector('english', content)) stored,
  token_count int not null default 0,
  citation_label text not null default ''
);
create index knowledge_chunks_hnsw on knowledge_chunks using hnsw (embedding vector_cosine_ops);
create index knowledge_chunks_tsv on knowledge_chunks using gin (tsv);
create index knowledge_chunks_tags on knowledge_chunks using gin (tags);
create index knowledge_chunks_scope on knowledge_chunks (scope, doc_type);

create table eval_sets (
  id bigserial primary key,
  agent_key text not null,
  name text not null,
  input jsonb not null,
  expected jsonb not null
);

create table eval_runs (
  id bigserial primary key,
  campaign_id text references campaigns(id),
  agent_key text not null,
  prompt_version_id text,
  score double precision not null,
  passed int not null default 0,
  total int not null default 0,
  detail jsonb not null default '{}',
  judge_notes text,
  created_at timestamptz not null default now()
);
