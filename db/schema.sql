-- Market-intel platform — Supabase schema (P2)
-- Run this in the Supabase SQL editor. Single-user personal tool: backend uses the
-- service role, so RLS is left OFF. If this ever goes multi-user, enable RLS on every
-- table and add per-user policies before exposing any anon/auth key.

-- Every `scanner.run <signal>` invocation (with --save)
create table if not exists scan_runs (
  id           bigint generated always as identity primary key,
  signal_name  text not null,                 -- 'buyback_arb', 'mean_reversion', ...
  verdict      text not null,                 -- signal's verdict snapshot at run time
  run_at       timestamptz not null default now(),
  params       jsonb not null default '{}',
  n_candidates integer not null default 0
);

-- Raw per-run candidates (generic across signals; payload holds signal-specifics)
create table if not exists candidates (
  id          bigint generated always as identity primary key,
  run_id      bigint not null references scan_runs(id) on delete cascade,
  signal_name text not null,
  symbol      text not null,
  score       numeric,                         -- ranking metric (e.g. est_return)
  payload     jsonb not null default '{}',
  created_at  timestamptz not null default now()
);
create index if not exists idx_candidates_symbol on candidates(symbol);
create index if not exists idx_candidates_run on candidates(run_id);

-- Buyback master — upserted on chittorgarh_id; the curated tracking universe (the edge)
create table if not exists buybacks (
  id                bigint generated always as identity primary key,
  chittorgarh_id    integer unique,            -- source id -> idempotent upserts
  company           text,
  symbol            text,
  buyback_price     numeric,
  record_date       date,
  close_date        date,
  entitlement_small numeric,                   -- guaranteed-acceptance floor
  est_return        numeric,                   -- latest computed floor estimate
  status            text not null default 'open',  -- open|tendered|settled|skipped
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

-- Your manual tender decision
create table if not exists tenders (
  id            bigint generated always as identity primary key,
  buyback_id    bigint not null references buybacks(id),
  decided_on    date not null,
  shares_bought integer,
  avg_cost      numeric,
  capital       numeric,                       -- deployed (<= 2L for small-shareholder)
  tendered      boolean not null default true,
  notes         text,
  created_at    timestamptz not null default now()
);

-- Realized outcome — the feedback that calibrates acceptance estimates
create table if not exists outcomes (
  id                  bigint generated always as identity primary key,
  tender_id           bigint not null references tenders(id) on delete cascade,
  accepted_shares     integer,
  realized_acceptance numeric,                 -- accepted / tendered (the key learning)
  residual_sold_price numeric,
  realized_return     numeric,
  recorded_at         timestamptz not null default now()
);
