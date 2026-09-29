-- RowSeer student-demo RLS: allow the anon key full access to profiles + practices.
-- Run this once in the Supabase SQL Editor (Dashboard → SQL → New query).
-- WARNING: insecure by design for coursework demos. Do not use in production.

alter table profiles enable row level security;
alter table practices enable row level security;

-- Drop existing policies with the same names if you re-run this script.
drop policy if exists "anon all profiles" on profiles;
drop policy if exists "anon all practices" on practices;

create policy "anon all profiles"
  on profiles
  for all
  to anon
  using (true)
  with check (true);

create policy "anon all practices"
  on practices
  for all
  to anon
  using (true)
  with check (true);

-- Ensure the anon role can use the API tables.
grant usage on schema public to anon;
grant select, insert, update, delete on table profiles to anon;
grant select, insert, update, delete on table practices to anon;
