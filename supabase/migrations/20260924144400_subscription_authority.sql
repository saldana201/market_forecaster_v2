create table public.subscriptions (
  user_id uuid primary key references auth.users(id) on delete cascade,
  plan text not null default 'demo',
  status text not null default 'none',
  stripe_customer_id text unique,
  stripe_subscription_id text unique,
  stripe_price_id text,
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint subscriptions_plan_check check (plan in ('demo','standard','pro')),
  constraint subscriptions_status_check check (
    status in (
      'none','trialing','active','past_due','unpaid',
      'canceled','incomplete','incomplete_expired','paused'
    )
  )
);

create trigger subscriptions_set_updated_at
before update on public.subscriptions
for each row execute function private.set_updated_at();

alter table public.subscriptions enable row level security;

create policy subscriptions_owner_read
on public.subscriptions
for select
to authenticated
using ((select auth.uid()) = user_id);

revoke all on table public.subscriptions from public, anon, authenticated, service_role;
grant select on table public.subscriptions to authenticated;
grant select, insert, update, delete on table public.subscriptions to service_role;

create index subscriptions_status_idx on public.subscriptions(status);
create index subscriptions_price_idx on public.subscriptions(stripe_price_id);
