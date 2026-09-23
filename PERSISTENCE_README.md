# Market Forecaster 4.1.2 — Persistent User Data

4.1.2 adds account-owned persistence on Supabase while keeping the anonymous Demo session-only.

## Azure App Service settings

Enable persistence only after 4.1.1 authentication is configured:

    MARKET_FORECASTER_AUTH_PROVIDER=supabase
    MARKET_FORECASTER_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
    MARKET_FORECASTER_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
    MULTI_USER_ENABLED=true
    DATABASE_PERSISTENCE_ENABLED=true

Do not place a Supabase secret/service-role key in the Streamlit user-data path.

## Ownership model

Every authenticated Data API request sends:

- the application publishable key
- the signed-in user's Supabase access token

Postgres RLS derives auth.uid() from the verified JWT.

User-owned tables use the Supabase Auth UUID in user_id:

- profiles
- watchlists
- watchlist_items
- portfolios
- portfolio_positions
- saved_forecasts
- user_preferences

The browser cannot choose the authorization owner. Market Forecaster derives it from the verified auth subject.

## RLS

All public user-data tables have RLS enabled.

Policies use the pattern:

    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id)

Anonymous access is revoked. Authenticated CRUD privileges are explicit.

## Phase boundary

4.1.2 persists watchlists and portfolios in the UI.

The schema also establishes saved_forecasts and user_preferences for subsequent wiring.
Stripe/subscription synchronization remains 4.1.3.
