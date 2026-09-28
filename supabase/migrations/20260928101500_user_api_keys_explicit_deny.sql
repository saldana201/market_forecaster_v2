drop policy if exists user_api_keys_deny_browser_roles
on public.user_api_keys;

create policy user_api_keys_deny_browser_roles
on public.user_api_keys
for all
to anon, authenticated
using (false)
with check (false);
