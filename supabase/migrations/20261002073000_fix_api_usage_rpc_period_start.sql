-- Fix PL/pgSQL output-column ambiguity in monthly Pro API usage metering.

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
  on conflict on constraint api_usage_monthly_pkey do nothing;

  update public.api_usage_monthly as usage
  set
    request_count = usage.request_count + 1,
    updated_at = timezone('utc', now())
  where
    usage.user_id = p_user_id
    and usage.period_start = v_period_start
    and usage.request_count < p_monthly_limit
  returning usage.request_count into v_used;

  if v_used is not null then
    v_allowed := true;
  else
    select usage.request_count
      into v_used
    from public.api_usage_monthly as usage
    where
      usage.user_id = p_user_id
      and usage.period_start = v_period_start;

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
