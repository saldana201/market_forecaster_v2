create table public.shared_forecast_contracts (
  ticker text primary key,
  contract_id text not null,
  generated_at timestamptz not null,
  as_of text,
  status text not null,
  schema_version text,
  contract jsonb not null,
  updated_at timestamptz not null default timezone('utc', now()),
  constraint shared_forecast_contracts_ticker_check
    check (ticker ~ '^[A-Z0-9._-]{1,20}$'),
  constraint shared_forecast_contracts_status_check
    check (status in ('READY','PARTIAL','UNAVAILABLE')),
  constraint shared_forecast_contracts_contract_object
    check (jsonb_typeof(contract) = 'object')
);

create trigger shared_forecast_contracts_set_updated_at
before update on public.shared_forecast_contracts
for each row execute function private.set_updated_at();

alter table public.shared_forecast_contracts enable row level security;

create policy shared_forecast_contracts_public_read
on public.shared_forecast_contracts
for select
to anon, authenticated
using (true);

revoke all on table public.shared_forecast_contracts
  from public, anon, authenticated, service_role;

grant select on table public.shared_forecast_contracts to anon, authenticated;
grant select, insert, update, delete
  on table public.shared_forecast_contracts to service_role;

create index shared_forecast_contracts_generated_idx
  on public.shared_forecast_contracts(generated_at desc);
