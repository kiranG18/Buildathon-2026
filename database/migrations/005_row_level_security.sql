-- Deny the Supabase anon and authenticated roles every table. The backend connects as the table owner, which bypasses RLS.
do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;
end $$;
