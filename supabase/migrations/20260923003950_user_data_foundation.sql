create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create or replace function private.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

revoke all on function private.set_updated_at() from public, anon, authenticated;

create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  timezone text not null default 'America/Chicago',
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint profiles_display_name_length check (
    display_name is null or char_length(display_name) between 1 and 120
  )
);

create table public.watchlists (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null default 'My Watchlist',
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint watchlists_name_length check (char_length(name) between 1 and 80),
  constraint watchlists_id_user_unique unique (id, user_id)
);

create unique index watchlists_user_name_unique
  on public.watchlists (user_id, lower(name));
create index watchlists_user_id_idx on public.watchlists(user_id);

create table public.watchlist_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  watchlist_id uuid not null,
  ticker text not null,
  notes text,
  sort_order integer not null default 0,
  created_at timestamptz not null default timezone('utc', now()),
  constraint watchlist_items_ticker_length check (char_length(ticker) between 1 and 20),
  constraint watchlist_items_notes_length check (notes is null or char_length(notes) <= 500),
  constraint watchlist_items_watchlist_user_fk
    foreign key (watchlist_id, user_id)
    references public.watchlists(id, user_id)
    on delete cascade,
  constraint watchlist_items_watchlist_ticker_unique unique (watchlist_id, ticker)
);

create index watchlist_items_user_id_idx on public.watchlist_items(user_id);
create index watchlist_items_watchlist_id_idx on public.watchlist_items(watchlist_id);

create table public.portfolios (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null default 'Primary Portfolio',
  currency text not null default 'USD',
  cash numeric(20,4) not null default 0,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint portfolios_name_length check (char_length(name) between 1 and 80),
  constraint portfolios_currency_format check (currency ~ '^[A-Z]{3}$'),
  constraint portfolios_id_user_unique unique (id, user_id)
);

create unique index portfolios_user_name_unique
  on public.portfolios (user_id, lower(name));
create index portfolios_user_id_idx on public.portfolios(user_id);

create table public.portfolio_positions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  portfolio_id uuid not null,
  ticker text not null,
  quantity numeric(24,8) not null,
  avg_cost numeric(20,6) not null default 0,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint portfolio_positions_ticker_length check (char_length(ticker) between 1 and 20),
  constraint portfolio_positions_quantity_positive check (quantity > 0),
  constraint portfolio_positions_avg_cost_nonnegative check (avg_cost >= 0),
  constraint portfolio_positions_portfolio_user_fk
    foreign key (portfolio_id, user_id)
    references public.portfolios(id, user_id)
    on delete cascade,
  constraint portfolio_positions_portfolio_ticker_unique unique (portfolio_id, ticker)
);

create index portfolio_positions_user_id_idx on public.portfolio_positions(user_id);
create index portfolio_positions_portfolio_id_idx on public.portfolio_positions(portfolio_id);

create table public.saved_forecasts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  ticker text not null,
  contract_version text,
  generated_at timestamptz,
  forecast_contract jsonb not null,
  created_at timestamptz not null default timezone('utc', now()),
  constraint saved_forecasts_ticker_length check (char_length(ticker) between 1 and 20),
  constraint saved_forecasts_contract_object check (jsonb_typeof(forecast_contract) = 'object')
);

create index saved_forecasts_user_id_idx on public.saved_forecasts(user_id);
create index saved_forecasts_user_ticker_created_idx
  on public.saved_forecasts(user_id, ticker, created_at desc);

create table public.user_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  default_ticker text,
  timezone text not null default 'America/Chicago',
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint user_preferences_default_ticker_length check (
    default_ticker is null or char_length(default_ticker) between 1 and 20
  ),
  constraint user_preferences_settings_object check (jsonb_typeof(settings) = 'object')
);

create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function private.set_updated_at();

create trigger watchlists_set_updated_at
before update on public.watchlists
for each row execute function private.set_updated_at();

create trigger portfolios_set_updated_at
before update on public.portfolios
for each row execute function private.set_updated_at();

create trigger portfolio_positions_set_updated_at
before update on public.portfolio_positions
for each row execute function private.set_updated_at();

create trigger user_preferences_set_updated_at
before update on public.user_preferences
for each row execute function private.set_updated_at();

alter table public.profiles enable row level security;
alter table public.watchlists enable row level security;
alter table public.watchlist_items enable row level security;
alter table public.portfolios enable row level security;
alter table public.portfolio_positions enable row level security;
alter table public.saved_forecasts enable row level security;
alter table public.user_preferences enable row level security;

create policy profiles_owner_all
on public.profiles
for all to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy watchlists_owner_all
on public.watchlists
for all to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy watchlist_items_owner_all
on public.watchlist_items
for all to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy portfolios_owner_all
on public.portfolios
for all to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy portfolio_positions_owner_all
on public.portfolio_positions
for all to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy saved_forecasts_owner_all
on public.saved_forecasts
for all to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy user_preferences_owner_all
on public.user_preferences
for all to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

revoke all on table public.profiles from anon;
revoke all on table public.watchlists from anon;
revoke all on table public.watchlist_items from anon;
revoke all on table public.portfolios from anon;
revoke all on table public.portfolio_positions from anon;
revoke all on table public.saved_forecasts from anon;
revoke all on table public.user_preferences from anon;

grant select, insert, update, delete on table public.profiles to authenticated;
grant select, insert, update, delete on table public.watchlists to authenticated;
grant select, insert, update, delete on table public.watchlist_items to authenticated;
grant select, insert, update, delete on table public.portfolios to authenticated;
grant select, insert, update, delete on table public.portfolio_positions to authenticated;
grant select, insert, update, delete on table public.saved_forecasts to authenticated;
grant select, insert, update, delete on table public.user_preferences to authenticated;

grant select, insert, update, delete on table public.profiles to service_role;
grant select, insert, update, delete on table public.watchlists to service_role;
grant select, insert, update, delete on table public.watchlist_items to service_role;
grant select, insert, update, delete on table public.portfolios to service_role;
grant select, insert, update, delete on table public.portfolio_positions to service_role;
grant select, insert, update, delete on table public.saved_forecasts to service_role;
grant select, insert, update, delete on table public.user_preferences to service_role;
