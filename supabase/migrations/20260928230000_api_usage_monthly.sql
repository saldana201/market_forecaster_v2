-- Account-wide monthly usage metering for Pro customer API access.

create table if not exists public.api_usage_monthly (
  user_id uuid not null references auth.users(id) on delete cascade,
  period_start date not null,
  request_count bigint not null default 0,
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (user_id, period_start),
  constraint api_usage_monthly_request_count_check
    check (request_count >= 0)
);

alter table public.api_usage_monthly enable row level security;

revoke all on table public.api_usage_monthly
  from public, anon, authenticated, service_role;
grant select, insert, update, delete on table public.api_usage_monthly
  to service_role;

drop policy if exists api_usage_monthly_deny_browser_roles
  on public.api_usage_monthly;

create policy api_usage_monthly_deny_browser_roles
on public.api_usage_monthly
for all
to anon, authenticated
using (false)
with check (false);

create index if not exists api_usage_monthly_user_period_idx
  on public.api_usage_monthly(user_id, period_start desc);

create or replace function public.consume_market_forecaster_api_request(
  p_user_id uuid,
  p_monthly_limit bigint
)
returns table (
  allowed boolean,
  used bigint,
  remaining bigint,
  period_start date,
  period_end date
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_period_start date := date_trunc('month', timezone('utc', now()))::date;
  v_period_end date := (
    date_trunc('month', timezone('utc', now())) + interval '1 month'
  )::date;
  v_used bigint;
  v_allowed boolean := false;
begin
  if p_user_id is null then
    raise exception 'user_id is required';
  end if;

  if p_monthly_limit <= 0 then
    raise exception 'monthly API request limit must be greater than zero';
  end if;

  insert into public.api_usage_monthly (
    user_id,
    period_start,
    request_count
  )
  values (
    p_user_id,
    v_period_start,
    0
  )
  on conflict (user_id, period_start) do nothing;

  update public.api_usage_monthly
  set
    request_count = request_count + 1,
    updated_at = timezone('utc', now())
  where
    user_id = p_user_id
    and period_start = v_period_start
    and request_count < p_monthly_limit
  returning request_count into v_used;

  if v_used is not null then
    v_allowed := true;
  else
    select request_count
      into v_used
    from public.api_usage_monthly
    where
      user_id = p_user_id
      and period_start = v_period_start;

    v_used := coalesce(v_used, p_monthly_limit);
  end if;

  return query
  select
    v_allowed,
    v_used,
    greatest(p_monthly_limit - v_used, 0),
    v_period_start,
    v_period_end;
end;
$$;

revoke all on function public.consume_market_forecaster_api_request(
  uuid, bigint
) from public, anon, authenticated;

grant execute on function public.consume_market_forecaster_api_request(
  uuid, bigint
) to service_role;
