create table if not exists public.browser_auth_sessions (
  handle_hash text primary key,
  auth_subject uuid not null references auth.users(id) on delete cascade,
  refresh_token_ciphertext text not null,
  user_agent_hash text not null,
  created_at timestamptz not null default timezone('utc', now()),
  last_seen_at timestamptz not null default timezone('utc', now()),
  expires_at timestamptz not null,
  revoked_at timestamptz,
  constraint browser_auth_sessions_handle_hash_check
    check (handle_hash ~ '^[a-f0-9]{64}$'),
  constraint browser_auth_sessions_user_agent_hash_check
    check (user_agent_hash ~ '^[a-f0-9]{64}$')
);

alter table public.browser_auth_sessions enable row level security;

revoke all on table public.browser_auth_sessions
  from public, anon, authenticated, service_role;

grant select, insert, update, delete
  on table public.browser_auth_sessions
  to service_role;

create index if not exists browser_auth_sessions_subject_idx
  on public.browser_auth_sessions(auth_subject);

create index if not exists browser_auth_sessions_expiry_idx
  on public.browser_auth_sessions(expires_at);

create index if not exists browser_auth_sessions_active_idx
  on public.browser_auth_sessions(auth_subject, expires_at)
  where revoked_at is null;
