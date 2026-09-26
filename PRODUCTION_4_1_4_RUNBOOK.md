# Market Forecaster 4.1.4 — Azure Production Hardening Runbook

This runbook covers the production-hardening items introduced in 4.1.4.

## 1. Shared Forecast Contract storage

Market Forecaster can now read the latest shared Forecast Contracts from Supabase and fall back to the deployment-local JSON cache.

Enable on Azure App Service only after the shared table contains current Demo contracts:

    SHARED_CONTRACT_STORAGE_ENABLED=true
    MARKET_FORECASTER_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
    MARKET_FORECASTER_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...

The Streamlit application needs only the publishable key to read shared contracts.

Do **not** put the Supabase service-role key in browser code.

## 2. Scheduled Demo refresh

The scheduled workflow is:

    .github/workflows/refresh_demo_contracts.yml

It runs after U.S. market close on trading-week days and can also be started manually.

The publisher is secretless from GitHub's perspective. GitHub Actions requests a
short-lived OIDC token with audience:

    market-forecaster-supabase

The Supabase `publish-demo-contracts` Edge Function verifies the token against
GitHub's public JWKS and pins the repository, master ref, workflow path, and
allowed event types before using Supabase's internal service-role credential.

No Supabase service-role key is stored in GitHub for Demo publishing.

The refresh flow:

1. obtains a short-lived GitHub OIDC token
2. fetches the active shared Forecast Authority
3. generates all 14 Demo Forecast Contracts locally
4. requires every contract to be READY
5. obtains a fresh OIDC token
6. publishes exactly the 14-contract Demo set
7. verifies every published row before returning success

## 3. Azure App Service baseline

Production App Service should retain:

    Python 3.12
    WebSockets enabled
    Health Check path /
    SCM_DO_BUILD_DURING_DEPLOYMENT=true
    ENABLE_ORYX_BUILD=true

Startup command:

    python -m streamlit run market_forecaster/app.py --server.address 0.0.0.0 --server.port 8000 --server.headless true

## 4. Azure application settings

Core:

    DEMO_MODE_ENABLED=true
    MULTI_USER_ENABLED=true
    DATABASE_PERSISTENCE_ENABLED=true
    SHARED_CONTRACT_STORAGE_ENABLED=true
    SHARED_AUTHORITY_ENABLED=true

Billing remains separately controlled:

    SUBSCRIPTIONS_ENABLED=false

until Stripe test-mode validation is complete.

Never store Supabase service-role or Stripe secret keys in source control.


### Persistent authenticated browser sessions

Authenticated Streamlit state now survives a hard browser refresh.

Architecture:
- the browser stores only a random opaque session handle in local storage
- Supabase access and refresh tokens are never stored in browser local storage
- the server stores the refresh token encrypted in `public.browser_auth_sessions`
- the encryption key is derived server-side from the existing Supabase service-role secret
- the session row is RLS-enabled and unavailable to anon/authenticated roles
- the session is bound to the browser user-agent hash
- default lifetime is 30 days unless the user signs out
- signing out revokes the server-side session and clears the browser handle

The Azure app therefore requires:

    MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY=<server-only secret>

for refresh-safe authenticated browser sessions as well as shared API rate limiting.

A temporary Supabase/Auth outage must not silently erase an existing browser session.
The UI should pause restoration and offer Retry instead of falling back to Demo.

The authenticated workspace also persists only a harmless page slug such as:

    ?view=account

No tokens or session handles are placed in the URL.

## 5. Backups

User data, subscriptions, and shared Forecast Contracts reside in Supabase Postgres.

Before paid public launch:
- confirm the Supabase project's backup/PITR policy matches the selected Supabase plan
- document restore ownership and recovery contacts
- test a restore procedure in a non-production environment

Git history is not a database backup.

## 6. Monitoring

Current safeguards:
- GitHub CI compile/lint/unit/container gates
- Azure deployment HTTP smoke test
- FastAPI /api/v1/health liveness endpoint
- FastAPI /api/v1/ready readiness endpoint
- structured request IDs/access logging
- Demo cache readiness script

Recommended Azure alerts:
- App Service 5xx rate
- response latency
- restart/container-start failures
- CPU and memory saturation
- failed deployment
- custom-domain TLS expiry if not managed automatically

## 7. Rate limiting

FastAPI supports a shared fixed-window limiter backed by the private Supabase
`api_rate_limit_buckets` table and the
`consume_market_forecaster_rate_limit` RPC.

For the trusted API host, configure:

    MARKET_FORECASTER_SHARED_RATE_LIMIT_ENABLED=true
    MARKET_FORECASTER_RATE_LIMIT_REQUESTS=30
    MARKET_FORECASTER_RATE_LIMIT_WINDOW_SECONDS=60
    MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY=<server-only secret>

The rate-limit RPC is executable only by the Supabase service role. Do not expose
that key to browser code or the public Demo frontend.

The limiter derives an HMAC bucket from the client identifier. Raw client IPs are
not persisted in Supabase. The HMAC secret comes from
`MARKET_FORECASTER_RATE_LIMIT_HASH_SECRET` when configured, otherwise the
production API key is used as the server-side secret.

If the shared backend is temporarily unavailable, RateLimitMiddleware falls back
to its existing per-process limiter so the API remains available.

For larger public API scale, Azure API Management or Front Door/WAF can still be
placed in front as an additional abuse-protection layer.

## 8. Secrets

Store production secrets only in:
- Azure App Service application settings / Key Vault references
- GitHub Actions repository/environment secrets
- Supabase Edge Function secrets

Never commit:
- Stripe secret key
- Stripe webhook signing secret
- Supabase service-role key
- production API key

## 9. Automated readiness gate

Run:

    python -m market_forecaster.scripts.production_readiness --strict

The command evaluates the configured deployment without printing credentials.

It checks:
- managed authentication configuration
- persistent browser-auth session configuration
- persistent user-data configuration
- shared Forecast Contract storage
- shared Forecast Authority
- all 14 Demo contracts
- Stripe subscription configuration
- shared API rate limiting

Stripe is a warning while subscriptions are intentionally disabled.

For a paid-public-launch gate, require billing too:

    python -m market_forecaster.scripts.production_readiness --strict --require-billing

A non-zero exit means at least one required production dependency is not ready.

## 10. Supabase security advisory review

The private API rate-limit bucket table is intentionally inaccessible to anon and
authenticated roles, and rate-limit mutations occur only through a service-role-only
SECURITY DEFINER RPC.

Supabase may still flag any RLS-disabled table as a security advisory. Treat that
as an explicit release review item rather than suppressing it. If RLS is enabled,
verify the trusted RPC still works before deploying the change.

## 11. Production cutover checklist

1. CI green.
2. Supabase migrations applied.
3. GitHub OIDC publisher workflow succeeds from master.
4. Run the shared refresh workflow manually once.
5. Confirm all 14 Demo contracts exist in public.shared_forecast_contracts.
6. Set SHARED_CONTRACT_STORAGE_ENABLED=true in Azure.
7. Restart App Service.
8. Verify all 14 Demo markets show live.
9. Verify a shared-store read outage still falls back to local contracts.
10. Verify two authenticated users remain isolated by RLS.
11. Sign in, open Account, hard-refresh the browser, and confirm the user remains signed in on Account.
12. Sign out and confirm a hard refresh returns to Demo.
13. Verify Stripe remains disabled until its separate test-mode acceptance is complete.
14. Run production_readiness --strict.
15. For paid launch, run production_readiness --strict --require-billing.
16. Verify Azure deployment and custom domain.
