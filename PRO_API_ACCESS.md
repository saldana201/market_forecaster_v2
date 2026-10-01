# Pro API Access

Market Forecaster Pro supports individually issued customer API keys for the protected FastAPI surface.

## Security model

Customer keys use this format:

    mfk_<random secret>

The plaintext key is shown once at creation time. The database stores only:

- a SHA-256 hash used for lookup
- a short non-secret prefix for identification
- the owning Supabase user ID
- created / last-used / revoked timestamps

The plaintext customer API key is never persisted.

The backing table is:

    public.user_api_keys

and is service-role-only. Browser roles (anon and authenticated) do not receive table privileges.

Apply:

    supabase/migrations/20260928100000_user_api_keys.sql

before enabling Pro customer API access.

## Entitlement boundary

A customer key is valid only when all of the following remain true:

1. SUBSCRIPTIONS_ENABLED=true
2. the key exists and has not been revoked
3. the key owner has a pro subscription row
4. subscription status is an entitled status (trialing, active, or past_due)

Subscription authority is checked on every customer-key request. A downgrade, cancellation, revocation, or disabled subscription feature therefore fails closed without requiring API key rotation.

The legacy/internal MARKET_FORECASTER_API_KEY remains supported for trusted server integrations and operational compatibility.

## Account experience

Active Pro users manage keys from:

    Account -> API Access

Each account may keep up to five active customer API keys.

After creating a key, copy it immediately. Market Forecaster cannot recover the full key later because only its hash is stored.

Keys can be revoked individually without changing the user's password or other API keys.

## Request authentication

Send a customer key in:

    X-API-Key: mfk_...

Example:

    curl -X POST https://<api-host>/api/v1/forecast \
      -H "X-API-Key: mfk_..." \
      -H "Content-Type: application/json" \
      -d '{"ticker":"AAPL"}'

/api/v1/health and /api/v1/ready remain operational endpoints and do not require API authentication. Protected forecasting/research routes use the customer key.

## Usage metering and included quota

Pro customer API access is now metered account-wide across all active API keys.

The initial launch quota is controlled by:

    MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS=1000

The value is configuration, not hard-coded pricing logic. It can be changed without
redeploying application code as the commercial API offering evolves.

Each authorized customer request atomically consumes one monthly request from
`public.api_usage_monthly`. The counter is service-role-only and resets on the
first day of each UTC month.

If the monthly quota is exhausted, customer requests fail with HTTP 429 rather
than being served without being metered.

Successful and quota-rejected customer responses expose:

    X-Market-Forecaster-API-Limit
    X-Market-Forecaster-API-Used
    X-Market-Forecaster-API-Remaining
    X-Market-Forecaster-API-Reset

Account -> API Access also shows current-month usage, remaining requests, and a
progress indicator.

## Rate limiting

The monthly quota is separate from short-window abuse protection.

All API traffic keeps the existing source-IP rate limit.

Requests presenting an mfk_ customer key additionally consume an independent
rate-limit bucket derived from a SHA-256 fingerprint of that key. Raw API keys
are never stored in limiter state.

When shared Supabase rate limiting is enabled, both buckets are shared across API
instances. If the shared limiter is unavailable, the existing in-process fallback
remains active.

## Deployment note

The current primary Azure App Service runs the Streamlit UI:

    python -m streamlit run market_forecaster/app.py ...

That UI host does not expose the FastAPI application.

The repository already contains a production API container at:

    market_forecaster/Dockerfile

which runs:

    uvicorn market_forecaster.api.main:app --host 0.0.0.0 --port 8000

Before advertising a public Pro API endpoint, deploy that FastAPI container (or an equivalent FastAPI App Service) on its own HTTPS API hostname and configure the same Supabase service-role setting used for customer API authorization.

The repository includes a manual-only GitHub workflow:

    .github/workflows/deploy_marketforecaster_api.yml

It deliberately does not create Azure resources. Provision the dedicated Azure Web App first, configure its required settings, then run **Deploy Market Forecaster Pro API** from GitHub Actions.

Minimum API-host settings include:

    MARKET_FORECASTER_ENV=production
    MARKET_FORECASTER_API_KEY=<internal server key>
    MARKET_FORECASTER_ALLOWED_ORIGINS=https://marketforecaster.oneeightaisystems.com
    MARKET_FORECASTER_SUPABASE_URL=<project URL>
    MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY=<server-only key>
    MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS=1000
    SUBSCRIPTIONS_ENABLED=true

Never expose the Supabase service-role key or internal API key to browser code.

After the API host is healthy, set this non-secret setting on the Streamlit UI App Service:

    MARKET_FORECASTER_API_PUBLIC_URL=https://<api-host>

The Account -> API Access panel will then show the API base URL and a link to the FastAPI documentation. There is intentionally no fallback to the Streamlit hostname because the UI host does not serve FastAPI routes.

## Production readiness

The production readiness gate now includes pro_api_key_store.

When billing is required or enabled, a missing/inaccessible API key table or API
usage-metering table is a release-blocking failure.
