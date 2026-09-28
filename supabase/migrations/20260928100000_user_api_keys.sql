-- Pro customer API keys. Plaintext API keys are never stored.

create table if not exists public.user_api_keys (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  key_prefix text not null,
  key_hash text not null unique,
  created_at timestamptz not null default timezone('utc', now()),
  last_used_at timestamptz,
  revoked_at timestamptz,
  constraint user_api_keys_name_check
    check (char_length(trim(name)) between 1 and 80),
  constraint user_api_keys_prefix_check
    check (key_prefix ~ '^mfk_[A-Za-z0-9_-]{6,20}$'),
  constraint user_api_keys_hash_check
    check (key_hash ~ '^[a-f0-9]{64}$')
);

alter table public.user_api_keys enable row level security;

revoke all on table public.user_api_keys from public, anon, authenticated, service_role;
grant select, insert, update, delete on table public.user_api_keys to service_role;

create index if not exists user_api_keys_user_id_idx
  on public.user_api_keys(user_id);

create index if not exists user_api_keys_active_idx
  on public.user_api_keys(user_id, revoked_at, created_at desc);

create index if not exists user_api_keys_last_used_idx
  on public.user_api_keys(last_used_at desc);
