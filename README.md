# RowSeer

A training log for college rowing: sign up, save practices per account, and track volume and pace with interactive charts.

## Features

- Email/password signup and login (custom auth via Supabase + bcrypt — not magic links)
- Per-user practice storage in Supabase (`profiles`, `practices`)
- Sidebar form to add water / erg / race sessions
- Practice table with computed `/500m` pace
- Weekly meters and pace-over-time Plotly charts
- Optional CSV download of your log

## Supabase setup (required once)

### 1. Tables

If you have not already created them:

```sql
create table profiles (
  id uuid primary key,
  email text unique not null,
  password_hash text not null,
  created_at timestamptz default now()
);

create table practices (
  id uuid primary key,
  user_id uuid references profiles(id) on delete cascade,
  practice_date date not null,
  type text check (type in ('water', 'erg', 'race')),
  distance_m int,
  time_sec int,
  notes text,
  created_at timestamptz default now()
);
```

### 2. Run RLS policies for the anon key

This demo uses the **anon** key with PostgREST (no Supabase Auth). Run the SQL in [`supabase_rls.sql`](supabase_rls.sql) in the Supabase SQL Editor so `anon` can insert/select on both tables.

**Exact SQL the user must run:**

```sql
alter table profiles enable row level security;
alter table practices enable row level security;

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

grant usage on schema public to anon;
grant select, insert, update, delete on table profiles to anon;
grant select, insert, update, delete on table practices to anon;
```

> These policies are intentionally open for a student demo. Do not ship them to production.

### 3. Streamlit secrets

Create `.streamlit/secrets.toml` locally (gitignored):

```toml
[supabase]
url = "https://YOUR_PROJECT.supabase.co"
anon_key = "YOUR_ANON_KEY"
```

On **Streamlit Community Cloud**, open the app → **Settings → Secrets** and paste the same block.

Find `url` and `anon` key under Supabase → Project Settings → API.

## Run locally

```bash
cd ~/Downloads/rowseer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# add .streamlit/secrets.toml as above
streamlit run app.py
```

## Redeploy notes (Streamlit Cloud)

1. Push the updated repo (include `src/db.py`, `supabase_rls.sql`, updated `app.py` / `requirements.txt`).
2. Confirm Cloud secrets contain the `[supabase]` block.
3. Run `supabase_rls.sql` in the Supabase SQL Editor if you have not already.
4. Redeploy / reboot the app so new dependencies (`bcrypt`, `requests`) install.

## Tech stack

- **Python** / **Streamlit** / **pandas** / **Plotly**
- **Supabase PostgREST** via `requests` + **bcrypt** password hashes in `profiles`

## Data schema (app columns)

Practices use `date`, `type`, `distance_m`, `time_sec`, and `notes`. In Supabase the date column is `practice_date`. Types: `water`, `erg`, `race`.
