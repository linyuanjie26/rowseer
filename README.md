# RowSeer

A training log for rowing: sign up, save practices per account, and track volume and pace with interactive charts.

## Features

- Email/password signup and login (custom auth via Supabase + bcrypt — not magic links)
- Per-user practice storage in Supabase (`profiles`, `practices`)
- Sidebar form to add Water / Erg / Race sessions (placeholder: **Choose type**)
- **Workout templates** (Steady 10k, 4x2k, 8x500, …) — code-only; selecting one pre-fills distance and notes
- Practice table with Title Case types and computed `/500m` pace
- **Edit** and **delete** individual practices (expander list with form + delete button)
- **Clear all** practices behind a confirmation checkbox
- **Goals & PRs**: season meter goal in Supabase (`user_goals`), progress bar, best `/500m` on pieces ≥1,000m and ≥2,000m (PRs computed from practices)
- Weekly meters and pace-over-time Plotly charts
- Optional CSV download of your log
- RowSeer branding throughout (no personal name-drop)

## Resume

- **RowSeer:** rowing practice tracker with Supabase auth, per-user logs, pace/volume charts, season goals & PRs, and CSV import/export.

## Roadmap

| Phase | Focus | Status |
|-------|--------|--------|
| **1** | Edit / delete practices, clear-all, type UX polish | **Implemented** |
| **2** | Richer fields: stroke rate, boat class, splits (`supabase_migrate_phase2.sql`) | Schema stub only — leave unused if absent |
| **3** | Filters / search by date range and type | Planned |
| **4** | Season / goal targets and progress meters | **Implemented** (this pass) |
| **5** | Team / coach share views (still per-user RLS) | Planned |
| **6** | PDF / printable season summary (e.g. reportlab) | Planned — not in this pass |
| **7** | Mobile-friendly layout polish and PWA-ish install tip | Planned |

Optional Phase 2 columns are documented in [`supabase_migrate_phase2.sql`](supabase_migrate_phase2.sql). Do **not** run that migration until the app writes those fields; the app ignores them if absent.

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

This demo uses the **anon** key with PostgREST (no Supabase Auth). Run the SQL in [`supabase_rls.sql`](supabase_rls.sql) in the Supabase SQL Editor so `anon` can insert/select/update/delete on both tables.

**Exact SQL the user must run** (also in `supabase_rls.sql`):

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

### 3. Season goals table (Goals & PRs)

Run [`supabase_goals.sql`](supabase_goals.sql) once so the app can store a per-user season meter goal:

```sql
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
```

PRs (best pace ≥1k / ≥2k) are computed in the app from `practices` — no extra columns required.

### 4. Streamlit secrets

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

1. Push the updated repo (include `src/db.py`, `src/metrics.py`, `app.py`, SQL files, `README.md`).
2. Confirm Cloud secrets contain the `[supabase]` block.
3. Run `supabase_rls.sql` if you have not already (needed for **update** / **delete**).
4. Run **`supabase_goals.sql`** once for season goals.
5. Redeploy / reboot the app so dependencies install.
6. **Do not** require `supabase_migrate_phase2.sql` until you adopt stroke_rate / boat_class.

## Tech stack

- **Python** / **Streamlit** / **pandas** / **Plotly**
- **Supabase PostgREST** via `requests` + **bcrypt** password hashes in `profiles`

## Data schema (app columns)

Practices load `id`, `date`, `type`, `distance_m`, `time_sec`, and `notes`. In Supabase the date column is `practice_date`. Types stored lowercase (`water`, `erg`, `race`) and shown Title Case in the UI. CSV export uses the data columns only (no `id`). Season goals live in `user_goals` (`user_id`, `season_meter_goal`, `updated_at`).
