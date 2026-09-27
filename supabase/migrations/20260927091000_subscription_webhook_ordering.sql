-- Harden Stripe subscription authority against duplicate and out-of-order webhook delivery.

alter table public.subscriptions
  add column if not exists stripe_event_id text,
  add column if not exists stripe_event_type text,
  add column if not exists stripe_event_created_at timestamptz;

create unique index if not exists subscriptions_stripe_event_id_key
  on public.subscriptions(stripe_event_id)
  where stripe_event_id is not null;

create index if not exists subscriptions_stripe_event_created_at_idx
  on public.subscriptions(stripe_event_created_at);

create or replace function public.apply_market_forecaster_subscription_event(
  p_user_id uuid,
  p_plan text,
  p_status text,
  p_stripe_customer_id text,
  p_stripe_subscription_id text,
  p_stripe_price_id text,
  p_current_period_end timestamptz,
  p_cancel_at_period_end boolean,
  p_stripe_event_id text,
  p_stripe_event_type text,
  p_stripe_event_created_at timestamptz
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  applied_user_id uuid;
begin
  if p_user_id is null then
    raise exception 'user_id is required';
  end if;

  if p_plan not in ('demo', 'standard', 'pro') then
    raise exception 'invalid subscription plan';
  end if;

  if p_status not in (
    'none', 'trialing', 'active', 'past_due', 'unpaid',
    'canceled', 'incomplete', 'incomplete_expired', 'paused'
  ) then
    raise exception 'invalid subscription status';
  end if;

  if nullif(trim(coalesce(p_stripe_event_id, '')), '') is null then
    raise exception 'stripe event id is required';
  end if;

  if nullif(trim(coalesce(p_stripe_event_type, '')), '') is null then
    raise exception 'stripe event type is required';
  end if;

  if p_stripe_event_created_at is null then
    raise exception 'stripe event created timestamp is required';
  end if;

  insert into public.subscriptions (
    user_id,
    plan,
    status,
    stripe_customer_id,
    stripe_subscription_id,
    stripe_price_id,
    current_period_end,
    cancel_at_period_end,
    stripe_event_id,
    stripe_event_type,
    stripe_event_created_at
  )
  values (
    p_user_id,
    p_plan,
    p_status,
    p_stripe_customer_id,
    p_stripe_subscription_id,
    p_stripe_price_id,
    p_current_period_end,
    coalesce(p_cancel_at_period_end, false),
    p_stripe_event_id,
    p_stripe_event_type,
    p_stripe_event_created_at
  )
  on conflict (user_id) do update
  set
    plan = excluded.plan,
    status = excluded.status,
    stripe_customer_id = excluded.stripe_customer_id,
    stripe_subscription_id = excluded.stripe_subscription_id,
    stripe_price_id = excluded.stripe_price_id,
    current_period_end = excluded.current_period_end,
    cancel_at_period_end = excluded.cancel_at_period_end,
    stripe_event_id = excluded.stripe_event_id,
    stripe_event_type = excluded.stripe_event_type,
    stripe_event_created_at = excluded.stripe_event_created_at
  where
    public.subscriptions.stripe_event_created_at is null
    or excluded.stripe_event_created_at >= public.subscriptions.stripe_event_created_at
  returning user_id into applied_user_id;

  return applied_user_id is not null;
end;
$$;

revoke all on function public.apply_market_forecaster_subscription_event(
  uuid, text, text, text, text, text, timestamptz, boolean, text, text, timestamptz
) from public, anon, authenticated;

grant execute on function public.apply_market_forecaster_subscription_event(
  uuid, text, text, text, text, text, timestamptz, boolean, text, text, timestamptz
) to service_role;
