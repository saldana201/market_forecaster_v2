drop policy if exists browser_auth_sessions_deny_browser_roles
on public.browser_auth_sessions;

create policy browser_auth_sessions_deny_browser_roles
on public.browser_auth_sessions
for all
to anon, authenticated
using (false)
with check (false);
