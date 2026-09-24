alter table public.saved_forecasts
  add column if not exists contract_id text;

update public.saved_forecasts
set contract_id = forecast_contract->>'contract_id'
where contract_id is null
  and forecast_contract ? 'contract_id';

delete from public.saved_forecasts
where contract_id is null or btrim(contract_id) = '';

alter table public.saved_forecasts
  alter column contract_id set not null;

alter table public.saved_forecasts
  add constraint saved_forecasts_user_contract_unique
  unique (user_id, contract_id);

create index if not exists saved_forecasts_user_created_idx
  on public.saved_forecasts(user_id, created_at desc);
