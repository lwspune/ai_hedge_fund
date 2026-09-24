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

-- ============================================================================
-- Infra I1 — company master (scanner/master.py, loaded by scripts/refresh_companies.py)
-- ============================================================================
create table if not exists companies (
  symbol       text primary key,
  isin         text unique check (isin ~ '^IN[A-Z0-9]{10}$'),
  name         text,
  series       text,                         -- EQ | BE | BZ (NSE EQUITY_L)
  listing_date date,
  face_value   numeric check (face_value is null or face_value > 0),
  industry     text,                         -- niftyindices (Total Market coverage)
  indices      text[] not null default '{}', -- nifty50, niftynext50, midcap150, ...
  is_financial boolean,                      -- industry = 'Financial Services'; null = unknown
  status       text not null default 'listed' check (status in ('listed','delisted')),
  delisted_on  date,
  updated_at   timestamptz not null default now(),
  check ((status = 'delisted') = (delisted_on is not null))
);
create index if not exists idx_companies_industry on companies(industry);
create index if not exists idx_companies_indices on companies using gin(indices);

create table if not exists symbol_changes (
  id         bigint generated always as identity primary key,
  company    text,
  old_symbol text not null,
  new_symbol text not null,
  changed_on date not null,
  unique (old_symbol, new_symbol, changed_on)
);
create index if not exists idx_symchg_old on symbol_changes(old_symbol);

alter table companies      enable row level security;
alter table symbol_changes enable row level security;
create policy "anon read companies"      on companies      for select to anon using (true);
create policy "anon read symbol_changes" on symbol_changes for select to anon using (true);

-- ============================================================================
-- Infra I3 — events calendar (scanner/events.py, loaded by scripts/refresh_events.py)
-- ============================================================================
create table if not exists ipos (
  id               bigint generated always as identity primary key,
  chittorgarh_id   integer not null unique,
  symbol           text not null,
  company          text,
  board            text not null check (board in ('mainboard','sme')),
  listing_at       text,
  issue_open       date,
  issue_close      date,
  boa_date         date,                     -- basis of allotment
  listing_date     date not null,
  issue_price      numeric not null check (issue_price > 0),
  listing_close    numeric check (listing_close is null or listing_close > 0),
  anchor_shares    bigint check (anchor_shares is null or anchor_shares >= 0),
  shares_allotted  bigint check (shares_allotted is null or shares_allotted >= 0),
  anchor_lockin_30 date,                     -- 50% of anchor shares unlock
  anchor_lockin_90 date,                     -- remaining anchor shares unlock
  updated_at       timestamptz not null default now(),
  check (anchor_lockin_30 is null or anchor_lockin_30 >= listing_date - 7),
  check (anchor_lockin_90 is null or anchor_lockin_30 is null or anchor_lockin_90 >= anchor_lockin_30)
);
create index if not exists idx_ipos_symbol on ipos(symbol);
create index if not exists idx_ipos_listing on ipos(listing_date);

create table if not exists corporate_events (
  id          bigint generated always as identity primary key,
  symbol      text not null,
  event_type  text not null check (event_type in ('bonus','split','consolidation','rights',
                'dividend','buyback','demerger','fo_ban','ipo_listing','anchor_lockin_30','anchor_lockin_90')),
  event_date  date not null,                 -- ex-date / ban trade date / listing / unlock date
  record_date date,
  details     jsonb not null default '{}',   -- ratio, amounts, face values, anchor size, ...
  source      text not null check (source in ('nse_ca','nse_fo','chittorgarh')),
  created_at  timestamptz not null default now(),
  unique (symbol, event_type, event_date, source)
);
create index if not exists idx_events_date on corporate_events(event_date);
create index if not exists idx_events_type_date on corporate_events(event_type, event_date);

alter table ipos             enable row level security;
alter table corporate_events enable row level security;
create policy "anon read ipos"             on ipos             for select to anon using (true);
create policy "anon read corporate_events" on corporate_events for select to anon using (true);

-- ============================================================================
-- Infra I4 — fundamentals snapshot (scanner/fundamentals.py, scripts/refresh_fundamentals.py).
-- Full statement history stays local: cache/fundamentals/<SYM>.parquet (free-tier size).
-- ============================================================================
create table if not exists company_snapshot (
  symbol          text primary key references companies(symbol) on update cascade,
  consolidated    boolean not null,
  market_cap_cr   numeric check (market_cap_cr is null or market_cap_cr >= 0),
  price           numeric check (price is null or price > 0),
  pe              numeric,
  book_value      numeric,
  dividend_yield  numeric check (dividend_yield is null or dividend_yield >= 0),
  roce            numeric,
  roe             numeric,
  face_value      numeric check (face_value is null or face_value > 0),
  high_52w        numeric,
  low_52w         numeric,
  revenue_ttm     numeric,
  net_profit_ttm  numeric,
  debt_to_equity  numeric check (debt_to_equity is null or debt_to_equity >= 0),  -- null for financials
  promoter_pct    numeric check (promoter_pct between 0 and 100),
  fii_pct         numeric check (fii_pct between 0 and 100),
  dii_pct         numeric check (dii_pct between 0 and 100),
  govt_pct        numeric check (govt_pct between 0 and 100),
  public_pct      numeric check (public_pct between 0 and 100),   -- retail-holding proxy
  n_shareholders  bigint check (n_shareholders is null or n_shareholders >= 0),
  shp_period      date,
  sector          text,                      -- screener 4-level taxonomy
  broad_industry  text,
  industry        text,
  basic_industry  text,
  fetched_at      timestamptz not null default now()
);
create index if not exists idx_snapshot_sector on company_snapshot(sector);
-- Infra I5: compact per-period series for the dashboard company page (history_json)
alter table company_snapshot add column if not exists history jsonb;
alter table company_snapshot add constraint company_snapshot_history_shape
  check (history is null or (jsonb_typeof(history) = 'object'
         and history ? 'annual' and history ? 'quarterly' and history ? 'shareholding'));
alter table company_snapshot enable row level security;
create policy "anon read company_snapshot" on company_snapshot for select to anon using (true);

-- Atomic per-date reload of market_deals (delete + insert in one transaction).
-- Used by scripts/refill_deals.py; service-role only.
create or replace function public.reload_market_deals(p_date date, p_rows jsonb)
returns integer
language plpgsql
security invoker
set search_path = public
as $$
declare n integer;
begin
  delete from market_deals where deal_date = p_date;
  insert into market_deals (deal_date, symbol, security, client, side, qty, price, value, kind)
  select deal_date, symbol, security, client, side, qty, price, value, kind
  from jsonb_populate_recordset(null::market_deals, p_rows)
  where deal_date = p_date;
  get diagnostics n = row_count;
  return n;
end $$;
revoke execute on function public.reload_market_deals(date, jsonb) from public, anon, authenticated;
grant execute on function public.reload_market_deals(date, jsonb) to service_role;

-- Private Storage bucket for full screener statement history (<SYM>.parquet), written by
-- scripts/refresh_fundamentals.py (service role). No policies -> anon cannot read it.
insert into storage.buckets (id, name, public, file_size_limit)
values ('fundamentals', 'fundamentals', false, 5242880)
on conflict (id) do nothing;
