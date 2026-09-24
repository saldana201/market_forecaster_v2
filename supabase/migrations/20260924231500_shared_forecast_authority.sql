create table public.shared_forecast_authority (
  authority_key text primary key,
  schema_version text not null,
  config jsonb not null,
  revision bigint not null default 1,
  updated_at timestamptz not null default timezone('utc', now()),
  constraint shared_forecast_authority_key_check check (authority_key = 'active'),
  constraint shared_forecast_authority_config_object check (jsonb_typeof(config) = 'object')
);

create trigger shared_forecast_authority_set_updated_at
before update on public.shared_forecast_authority
for each row execute function private.set_updated_at();

alter table public.shared_forecast_authority enable row level security;

create policy shared_forecast_authority_public_read
on public.shared_forecast_authority
for select
to anon, authenticated
using (true);

revoke all on table public.shared_forecast_authority
  from public, anon, authenticated, service_role;

grant select on table public.shared_forecast_authority to anon, authenticated;
grant select, insert, update, delete on table public.shared_forecast_authority to service_role;

insert into public.shared_forecast_authority (
  authority_key,
  schema_version,
  config,
  revision
)
values (
  'active',
  '4.0-authority-v1',
  '{
    "schema_version": "4.0-authority-v1",
    "horizons": {
      "1": {"model":"xgboost","context_family":"none","sector_ticker":null,"calibration_window":120,"enabled":true},
      "5": {"model":"xgboost","context_family":"none","sector_ticker":null,"calibration_window":120,"enabled":true},
      "10": {"model":"xgboost","context_family":"none","sector_ticker":null,"calibration_window":120,"enabled":true},
      "20": {"model":"xgboost","context_family":"none","sector_ticker":null,"calibration_window":120,"enabled":true}
    },
    "notes": [
      "Authority changes are explicit; research runs do not auto-promote models or feature families.",
      "Trading/execution decisions are outside this registry."
    ]
  }'::jsonb,
  1
)
on conflict (authority_key) do nothing;
