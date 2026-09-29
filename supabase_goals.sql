-- RowSeer season goals table + anon RLS (demo-friendly, same pattern as profiles/practices).
-- Run once in the Supabase SQL Editor after profiles exists.
-- PRs are computed client-side from practices; only the season meter goal is stored here.

create table if not exists user_goals (
  user_id uuid primary key references profiles(id) on delete cascade,
  season_meter_goal int,
  updated_at timestamptz default now()
);

alter table user_goals enable row level security;

drop policy if exists "anon all user_goals" on user_goals;

create policy "anon all user_goals"
  on user_goals
  for all
  to anon
  using (true)
  with check (true);

grant usage on schema public to anon;
grant select, insert, update, delete on table user_goals to anon;

comment on table user_goals is 'Per-user season meter goal; PRs stay client-side from practices.';
comment on column user_goals.season_meter_goal is 'Target total meters for the season (nullable until set).';
