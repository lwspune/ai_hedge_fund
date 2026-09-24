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

-- ============================================================================
-- Rights issues (scanner/events.parse_rights_page, scripts/refresh_events.py rights):
-- exact issue price, RE symbol and timetable per NSE rights issue (chittorgarh).
-- ============================================================================
create table if not exists rights_issues (
  id                 bigint generated always as identity primary key,
  chittorgarh_id     integer not null unique,
  symbol             text not null,
  company            text,
  isin               text,
  face_value         numeric check (face_value is null or face_value > 0),
  issue_price        numeric not null check (issue_price > 0),
  ratio_rights       integer check (ratio_rights is null or ratio_rights > 0),
  ratio_held         integer check (ratio_held is null or ratio_held > 0),
  issue_size_shares  bigint check (issue_size_shares is null or issue_size_shares > 0),
  record_date        date,
  re_credit_date     date,
  issue_open         date,
  renunciation_date  date,                   -- last day REs trade (market renunciation)
  issue_close        date,                   -- application deadline
  allotment_date     date,
  listing_date       date,
  re_symbol          text,                   -- NSE RE symbol (NDTVR, TILRR, SATIN-RE, ...)
  payment_terms      text,
  application_amount numeric check (application_amount is null or application_amount > 0),
  partly_paid        boolean not null default false,
  withdrawn          boolean not null default false,
  updated_at         timestamptz not null default now(),
  check (issue_close is null or issue_open is null or issue_close >= issue_open),
  check (application_amount is null or application_amount <= issue_price)
);
create index if not exists idx_rights_symbol on rights_issues(symbol);
create index if not exists idx_rights_open on rights_issues(issue_open);
alter table rights_issues enable row level security;
create policy "anon read rights_issues" on rights_issues for select to anon using (true);

-- ============================================================================
-- Filings index F1 (scanner/filings.py, scripts/refresh_filings.py): NSE corporate
-- announcements, material categories only, with the attachment (PDF) link.
-- ============================================================================
create table if not exists filings (
  seq_id         bigint primary key,           -- NSE announcement id
  symbol         text not null,
  isin           text,
  company        text,
  category       text not null,                -- NSE `desc`, e.g. 'Investor Presentation'
  subject        text,
  disclosed_at   timestamptz not null,
  attachment_url text check (attachment_url is null or attachment_url like 'https://%'),
  size_kb        numeric check (size_kb is null or size_kb >= 0),
  has_xbrl       boolean not null default false,
  created_at     timestamptz not null default now()
);
create index if not exists idx_filings_symbol_time on filings(symbol, disclosed_at desc);
create index if not exists idx_filings_category_time on filings(category, disclosed_at desc);
alter table filings enable row level security;
create policy "anon read filings" on filings for select to anon using (true);

-- ============================================================================
-- F3 filing KPIs (scanner/kpis.py rule_v1, scripts/extract_kpis.py). Every value carries the
-- exact quote it came from and its source filing. Chosen by docs/FILINGS_KPI_ANALYSIS.md.
-- ============================================================================
alter table filings add column if not exists extract_status text
  check (extract_status is null or extract_status in ('ok','no_pdf','error'));
alter table filings add column if not exists extracted_at timestamptz;
create index if not exists idx_filings_unextracted on filings(disclosed_at desc) where extracted_at is null;

create table if not exists company_kpis (
  id           bigint generated always as identity primary key,
  seq_id       bigint not null references filings(seq_id) on delete cascade,
  symbol       text not null,
  disclosed_at timestamptz not null,
  kpi          text not null check (kpi in ('order_book','order_win_value','capacity_utilisation','guidance')),
  value        numeric,
  unit         text,                        -- canonical: crore | lakh | mn | bn | lakh crore | USD mn | USD bn | %
  value_cr     numeric,                     -- INR crore equivalent (null for USD / %)
  as_of        date,
  quote        text not null check (length(quote) between 5 and 400),
  quote_hash   text generated always as (md5(quote)) stored,
  method       text not null default 'rule_v1',
  created_at   timestamptz not null default now(),
  unique (seq_id, kpi, quote_hash),
  check ((kpi = 'guidance') = (value is null)),
  check (kpi <> 'capacity_utilisation' or (value > 0 and value <= 100))
);
create index if not exists idx_kpis_symbol on company_kpis(symbol, kpi, disclosed_at desc);
alter table company_kpis enable row level security;
create policy "anon read company_kpis" on company_kpis for select to anon using (true);

-- Financials sector pack (scanner/kpis.fin_ratios): lender ratios, run only for Financial Services.
alter table company_kpis drop constraint if exists company_kpis_kpi_check;
alter table company_kpis add constraint company_kpis_kpi_check check (kpi in (
  'order_book','order_win_value','capacity_utilisation','guidance',
  'gnpa','nnpa','nim','credit_cost','pcr','crar','casa','roa'));
alter table company_kpis add constraint company_kpis_ratio_range check (
  kpi not in ('gnpa','nnpa','nim','credit_cost','pcr','crar','casa','roa')
  or (unit = '%' and value > 0 and value <= 100));

-- ============================================================================
-- Freshness monitoring (scripts/check_freshness.py, DATA_INFRA_SPEC WP2): database size for
-- the free-tier guard (PostgREST can't call pg_database_size directly). Service role only.
-- ============================================================================
create or replace function public.db_size_bytes()
returns bigint
language sql
security definer
set search_path = public
as $$ select pg_database_size(current_database()) $$;
revoke execute on function public.db_size_bytes() from public, anon, authenticated;
grant execute on function public.db_size_bytes() to service_role;

-- ============================================================================
-- WP6 calendar (scanner/events.py, scanner/trading_calendar.py, refresh_events.py
-- holidays|board-meetings|bands): NSE trading days, board meetings / results dates, price bands.
-- ============================================================================
create table if not exists trading_calendar (
  trade_date  date primary key,
  is_trading  boolean not null,
  description text,
  source      text not null default 'nse_holiday_master',
  check (extract(isodow from trade_date) < 6)           -- weekdays only; weekends are implicit
);
alter table trading_calendar enable row level security;
create policy "anon read trading_calendar" on trading_calendar for select to anon using (true);

alter table corporate_events drop constraint if exists corporate_events_event_type_check;
alter table corporate_events add constraint corporate_events_event_type_check check (event_type in (
  'bonus','split','consolidation','rights','dividend','buyback','demerger','fo_ban','ipo_listing',
  'anchor_lockin_30','anchor_lockin_90','board_meeting','results','band_change'));
alter table corporate_events drop constraint if exists corporate_events_source_check;
alter table corporate_events add constraint corporate_events_source_check check (source in (
  'nse_ca','nse_fo','chittorgarh','nse_bm','nse_band'));
create index if not exists idx_events_symbol_type_date on corporate_events(symbol, event_type, event_date);

-- ============================================================================
-- WP3 price store (scanner/bhavcopy.py, scripts/refresh_prices.py, pricestore source="db").
-- daily_prices = rolling ~2 years of NSE bhavcopy (equity series, UNADJUSTED closes);
-- the full history (all series/columns, 2020->) lives in the private `prices` bucket as
-- bhav/YYYY-MM.parquet. index_prices = benchmark closes (full history, tiny).
-- ============================================================================
create table if not exists daily_prices (
  symbol        text not null,
  trade_date    date not null,
  series        text not null check (series in ('EQ','BE','BZ','SM','ST','SZ')),
  close         real not null check (close > 0),
  prev_close    real check (prev_close is null or prev_close > 0),
  volume        bigint check (volume is null or volume >= 0),
  turnover_lakh real check (turnover_lakh is null or turnover_lakh >= 0),
  delivery_pct  real check (delivery_pct is null or (delivery_pct >= 0 and delivery_pct <= 100)),
  primary key (symbol, trade_date)
);
-- rows arrive in date order, so a BRIN index serves per-date deletes/counts at a few KB
-- (a btree would cost ~20 MB/yr of the 500 MB free tier)
create index if not exists idx_daily_prices_date_brin on daily_prices using brin (trade_date);
alter table daily_prices enable row level security;
create policy "anon read daily_prices" on daily_prices for select to anon using (true);

create table if not exists index_prices (
  index_symbol text not null,                 -- Yahoo ticker: ^NSEI, ^CRSLDX, ...
  trade_date   date not null,
  close        real not null check (close > 0),
  primary key (index_symbol, trade_date)
);
alter table index_prices enable row level security;
create policy "anon read index_prices" on index_prices for select to anon using (true);

-- Atomic per-date reload (delete + insert in one transaction), like reload_market_deals.
create or replace function public.reload_daily_prices(p_date date, p_rows jsonb)
returns integer
language plpgsql
security invoker
set search_path = public
as $$
declare n integer;
begin
  delete from daily_prices where trade_date = p_date;
  insert into daily_prices (symbol, trade_date, series, close, prev_close, volume, turnover_lakh, delivery_pct)
  select symbol, trade_date, series, close, prev_close, volume, turnover_lakh, delivery_pct
  from jsonb_populate_recordset(null::daily_prices, p_rows)
  where trade_date = p_date;
  get diagnostics n = row_count;
  return n;
end $$;
revoke execute on function public.reload_daily_prices(date, jsonb) from public, anon, authenticated;
grant execute on function public.reload_daily_prices(date, jsonb) to service_role;

-- Retention: drop table rows older than p_keep_days (the bucket keeps them). Weekly.
create or replace function public.prune_daily_prices(p_keep_days integer)
returns integer
language plpgsql
security invoker
set search_path = public
as $$
declare n integer;
begin
  if p_keep_days < 365 then
    raise exception 'refusing to keep fewer than 365 days (got %)', p_keep_days;
  end if;
  delete from daily_prices where trade_date < current_date - p_keep_days;
  get diagnostics n = row_count;
  return n;
end $$;
revoke execute on function public.prune_daily_prices(integer) from public, anon, authenticated;
grant execute on function public.prune_daily_prices(integer) to service_role;

-- Private bucket: bhav/YYYY-MM.parquet, the durable full bhavcopy history. No policies.
insert into storage.buckets (id, name, public, file_size_limit)
values ('prices', 'prices', false, 20971520)
on conflict (id) do nothing;
