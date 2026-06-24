-- Market-intel platform — Supabase schema (P2/P3)
-- Applied live via the Supabase MCP. RLS is ON: the anon key (dashboard / Vercel) can
-- READ only; all writes go through the service-role key (CLIs + edge functions), which
-- bypasses RLS. See the RLS section at the bottom.

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
  issue_size_cr     numeric,                   -- buyback size (crore); feeds acceptance model
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

-- Historical bulk/block deal warehouse (backfilled from cache; refreshed daily by the
-- refresh-deals edge function via per-date reload).
create table if not exists market_deals (
  id         bigint generated always as identity primary key,
  deal_date  date not null,
  symbol     text not null,
  security   text,
  client     text not null,
  side       text not null,           -- BUY | SELL
  qty        bigint,
  price      numeric,
  value      numeric,                 -- qty * price (rupees)
  kind       text not null,           -- bulk | block
  created_at timestamptz not null default now()
);
create index if not exists idx_deals_symbol on market_deals(symbol);
create index if not exists idx_deals_date on market_deals(deal_date);

-- RLS: anon (dashboard) reads only; service-role writes bypass RLS.
alter table scan_runs    enable row level security;
alter table candidates   enable row level security;
alter table buybacks     enable row level security;
alter table tenders      enable row level security;
alter table outcomes     enable row level security;
alter table market_deals enable row level security;
create policy "anon read scan_runs"    on scan_runs    for select to anon using (true);
create policy "anon read candidates"   on candidates   for select to anon using (true);
create policy "anon read buybacks"     on buybacks     for select to anon using (true);
create policy "anon read tenders"      on tenders      for select to anon using (true);
create policy "anon read outcomes"     on outcomes     for select to anon using (true);
create policy "anon read market_deals" on market_deals for select to anon using (true);

-- Edge functions (deployed via MCP, source in supabase/functions/): refresh-deals (NSE
-- bulk/block CSV → market_deals, per-date reload) and refresh-buybacks (chittorgarh id
-- probe → buybacks upsert). pg_cron job 'refresh-deals-daily' (33 14 * * 1-5 UTC ≈ 20:03
-- IST) calls refresh-deals via pg_net. Requires: create extension pg_cron; create extension pg_net;
