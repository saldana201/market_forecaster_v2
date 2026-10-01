# Market Forecaster API Monetization Plan

The Pro API should be treated as a revenue product, not only as a technical
integration surface.

This plan keeps the first launch simple while preserving a path to higher-margin
API tiers and enterprise contracts.

## Phase 1 — Pro included API access

Current product model:

- Standard: application access, persistence, exports; no customer API keys
- Pro: everything in Standard plus Research Lab, advanced diagnostics, and API access
- Pro API keys are individually generated, revocable, and stored only as hashes
- all customer API requests re-check active Pro subscription authority
- API usage is account-wide across all active keys

Initial included quota:

    MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS=1000

The quota is deliberately environment-configurable. It is an initial launch
allowance, not a permanent pricing rule.

This gives Pro customers enough capacity to build automations and integrations
while protecting forecasting compute from unlimited API consumption.

## Phase 2 — Measure economics before adding overages

Before selling larger API packages, collect:

- active API customers
- monthly requests per customer
- percentage of Pro customers creating an API key
- endpoint mix
- response/error rate
- p50 / p95 latency
- infrastructure and model-compute cost per request
- monthly quota exhaustion rate
- customer requests for higher limits

Do not introduce per-request billing until those measurements are available.

## Phase 3 — Paid API expansion

After real usage and compute-cost data is available, add one or both of:

### Pro API add-on

Keep the core Pro subscription and sell higher monthly request allowances as a
paid add-on.

Example packaging direction:

- Pro Included — current monthly allowance
- API Growth — larger monthly allowance
- API Business — high-volume allowance plus higher operational limits

Exact request counts and prices should be set from actual usage/cost data rather
than hard-coded now.

### API-first subscription

For customers who primarily need machine-to-machine access, introduce an API-only
commercial plan separate from the interactive Research Lab product.

That avoids forcing integration customers to buy UI features they do not need.

## Phase 4 — Metered overage

Stripe supports usage-based billing patterns that can be layered on after the
included quota model is proven.

The recommended future structure is:

1. subscription includes a fixed monthly request allowance
2. Market Forecaster usage authority records accepted billable requests
3. requests above the included allowance are either:
   - blocked until upgrade, or
   - billed as metered overage
4. Stripe remains payment authority while Supabase remains application usage
   authority

Do not report usage to Stripe directly from untrusted clients.

## API product design

The public API should emphasize stable, high-value contracts rather than exposing
every internal diagnostic route as a commercial promise.

Primary commercial surface:

- canonical forecast
- forecast probability / uncertainty
- signals
- portfolio analysis
- opportunity ranking
- selected research outputs

Internal/operational endpoints remain authenticated with the trusted internal
server key and are excluded from the public OpenAPI schema. Customer `mfk_` keys
cannot use governance/deployment operations merely because they have a Pro
subscription.

This separation lets the commercial API evolve as a stable product while internal
model-operations routes can change without creating public compatibility promises.

## Versioning

Keep customer-facing endpoints under:

    /api/v1/

Breaking changes should ship under a new major API version rather than silently
changing existing response contracts.

## Customer experience

Pro Account -> API Access should provide:

- create / revoke keys
- one-time plaintext key reveal
- API endpoint and documentation link
- current monthly usage
- included monthly quota
- remaining requests
- reset period
- examples for curl / Python
- clear upgrade path when quota is exhausted

## Revenue safeguards

The API should fail closed when any of these cannot be verified:

- customer API key
- active Pro/API entitlement
- usage meter
- quota authority

This prevents unbilled access during a billing or persistence outage.

## Launch sequence

1. Merge and apply API usage-metering migration. **Complete for the current Supabase project.**
2. Deploy the dedicated FastAPI Azure App Service.
3. Configure the initial Pro monthly allowance explicitly.
4. Verify API key creation and a protected forecast request.
5. Confirm usage increments and response quota headers.
6. Confirm Account -> API Access shows the same usage count.
7. Test quota exhaustion with a low temporary sandbox limit.
8. Restore the launch quota.
9. Start collecting usage/cost data.
10. Add paid API add-ons only after enough usage data exists to price them responsibly.
