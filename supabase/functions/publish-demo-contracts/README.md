# GitHub OIDC Demo publisher

This Supabase Edge Function is the trusted publishing boundary for the scheduled
Demo Forecast Contract refresh.

It does **not** use a GitHub-stored Supabase service-role key.

Authentication flow:

1. GitHub Actions requests a short-lived OIDC token.
2. The token audience is `market-forecaster-supabase`.
3. This function verifies the token against GitHub's public JWKS.
4. It requires:
   - repository: `saldana201/market_forecaster_v2`
   - ref: `refs/heads/master`
   - workflow: `.github/workflows/refresh_demo_contracts.yml`
   - event: `schedule` or `workflow_dispatch`
5. Only then does the function use Supabase's internal service-role environment
   to read shared Forecast Authority or publish shared Forecast Contracts.

The POST publisher requires all 14 Demo contracts, READY status, FORECAST_ONLY
scope, the canonical schema version, and the 1D/5D/10D/20D horizon set before
performing one upsert.

Deploy with JWT verification disabled because GitHub's OIDC token is not a
Supabase Auth JWT. The function performs its own cryptographic JWT verification.

    supabase functions deploy publish-demo-contracts --no-verify-jwt
