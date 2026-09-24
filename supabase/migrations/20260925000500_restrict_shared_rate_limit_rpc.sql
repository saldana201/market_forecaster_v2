revoke all on function public.consume_market_forecaster_rate_limit(text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.consume_market_forecaster_rate_limit(text, integer, integer)
  to service_role;
