revoke all on table public.profiles from public, anon, authenticated, service_role;
revoke all on table public.watchlists from public, anon, authenticated, service_role;
revoke all on table public.watchlist_items from public, anon, authenticated, service_role;
revoke all on table public.portfolios from public, anon, authenticated, service_role;
revoke all on table public.portfolio_positions from public, anon, authenticated, service_role;
revoke all on table public.saved_forecasts from public, anon, authenticated, service_role;
revoke all on table public.user_preferences from public, anon, authenticated, service_role;

grant select, insert, update, delete on table public.profiles to authenticated, service_role;
grant select, insert, update, delete on table public.watchlists to authenticated, service_role;
grant select, insert, update, delete on table public.watchlist_items to authenticated, service_role;
grant select, insert, update, delete on table public.portfolios to authenticated, service_role;
grant select, insert, update, delete on table public.portfolio_positions to authenticated, service_role;
grant select, insert, update, delete on table public.saved_forecasts to authenticated, service_role;
grant select, insert, update, delete on table public.user_preferences to authenticated, service_role;

alter default privileges for role postgres in schema public
  revoke all on tables from public, anon, authenticated, service_role;

alter default privileges for role postgres in schema public
  revoke all on sequences from public, anon, authenticated, service_role;

alter default privileges for role postgres in schema public
  revoke execute on functions from public, anon, authenticated, service_role;
