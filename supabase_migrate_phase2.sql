-- RowSeer Phase 2 piece-details columns.
-- Prefer running supabase_piece_details.sql (same columns). Kept for roadmap continuity.
-- Safe to re-run: uses IF NOT EXISTS.

alter table practices
  add column if not exists stroke_rate int,
  add column if not exists boat_class text,
  add column if not exists splits text;

comment on column practices.stroke_rate is 'Average or target stroke rate in spm; optional Phase 2.';
comment on column practices.boat_class is 'Boat class label e.g. 8+, 4-, 2x, 1x; optional Phase 2.';
comment on column practices.splits is 'Splits note or comma-separated /500m splits; optional Phase 2.';
