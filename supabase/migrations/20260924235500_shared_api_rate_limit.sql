create table private.api_rate_limit_buckets (
  bucket_key text primary key,
  window_started_at timestamptz not null,
  request_count integer not null default 0,
  updated_at timestamptz not null default timezone('utc', now()),
  constraint api_rate_limit_bucket_key_length
    check (char_length(bucket_key) between 16 and 128),
  constraint api_rate_limit_request_count_nonnegative
    check (request_count >= 0)
);

create index api_rate_limit_buckets_updated_idx
  on private.api_rate_limit_buckets(updated_at);

revoke all on table private.api_rate_limit_buckets
  from public, anon, authenticated, service_role;

create or replace function public.consume_market_forecaster_rate_limit(
  p_bucket_key text,
  p_limit integer,
  p_window_seconds integer
)
returns table (
  allowed boolean,
  request_count integer,
  retry_after_seconds integer
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_now timestamptz := clock_timestamp();
  v_started timestamptz;
  v_count integer;
  v_reset timestamptz;
begin
  if p_bucket_key is null
     or char_length(p_bucket_key) < 16
     or char_length(p_bucket_key) > 128 then
    raise exception 'invalid bucket key';
  end if;

  if p_limit < 1 or p_limit > 10000 then
    raise exception 'invalid rate limit';
  end if;

  if p_window_seconds < 1 or p_window_seconds > 3600 then
    raise exception 'invalid rate-limit window';
  end if;

  insert into private.api_rate_limit_buckets(
    bucket_key,
    window_started_at,
    request_count,
    updated_at
  )
  values (p_bucket_key, v_now, 0, v_now)
  on conflict (bucket_key) do nothing;

  select b.window_started_at, b.request_count
    into v_started, v_count
  from private.api_rate_limit_buckets as b
  where b.bucket_key = p_bucket_key
  for update;

  if v_started <= v_now - make_interval(secs => p_window_seconds) then
    v_started := v_now;
    v_count := 1;
  else
    v_count := v_count + 1;
  end if;

  update private.api_rate_limit_buckets as b
  set window_started_at = v_started,
      request_count = v_count,
      updated_at = v_now
  where b.bucket_key = p_bucket_key;

  v_reset := v_started + make_interval(secs => p_window_seconds);

  return query
  select
    v_count <= p_limit,
    v_count,
    greatest(0, ceil(extract(epoch from (v_reset - v_now)))::integer);
end;
$$;

revoke all on function public.consume_market_forecaster_rate_limit(text, integer, integer)
  from public;
grant execute on function public.consume_market_forecaster_rate_limit(text, integer, integer)
  to anon, authenticated, service_role;
