# Market Forecaster 4.1.1 — Authentication Foundation

This phase adds managed user identity without changing forecast math or Demo forecast quality.

## Provider

The first adapter is Supabase Auth. The rest of the application talks to the provider-neutral AuthProvider interface so the provider can be replaced later without rewriting product authorization.

Market Forecaster does not store or hash account passwords.

## Feature flag

Authentication remains off until explicitly enabled:

    MULTI_USER_ENABLED=true

Anonymous Demo access remains available whether authentication is enabled or not.

## Required environment settings

Set these as Azure App Service configuration values or local environment variables:

    MARKET_FORECASTER_AUTH_PROVIDER=supabase
    MARKET_FORECASTER_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
    MARKET_FORECASTER_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
    MULTI_USER_ENABLED=true

SUPABASE_URL and SUPABASE_ANON_KEY are accepted as fallback names.

Do not commit keys to the repository.

## Identity security

The application never accepts a user_id from the browser as authorization identity.

Flow:

    Bearer token
        -> managed provider verification
        -> provider subject
        -> deterministic internal Market Forecaster UUID
        -> AppIdentity

The internal UUID is stable for the same provider subject and different for another provider or subject. Email is display/account metadata only and is not the authorization key.

## Streamlit behavior

When multi-user mode is enabled and the provider is configured:

- Demo still opens anonymously.
- Account tab supports registration, login, and logout.
- Successful login upgrades the current session to an authenticated AppIdentity.
- Invalid or expired tokens fail closed and return the session to Demo identity.
- Persistent watchlists/portfolios are intentionally deferred to 4.1.2.

## API behavior

When multi-user mode is enabled:

    GET /api/v1/account/me

requires:

    Authorization: Bearer <access token>

The route derives user identity from the verified token. Query/body user_id values are not used for authorization.

## Phase boundary

4.1.1 does not add:

- PostgreSQL user data persistence
- persistent watchlists or portfolios
- Stripe
- subscription synchronization
- user-specific Forecast Authority
- broker or trading functionality

Those remain later 4.1 phases.
