# Market Forecaster — Project Status Runbook

Status date: 2026-09-30 (America/Chicago)

This document is the current launch-status checklist for Market Forecaster. It separates completed work from remaining release work and post-launch expansion.

## Executive status

Current state:

- Core Streamlit application is deployed and working on the custom domain.
- Authentication persistence, account storage, UI consistency, Standard/Pro entitlements, Stripe Checkout, Stripe Customer Portal, webhook synchronization, forecast exports, Pro API keys, API deployment workflow, and API usage-metering code are implemented.
- Standard and Pro Stripe sandbox subscriptions were user-tested successfully.
- Stripe Product Catalog shows both active recurring products at the intended sandbox prices:
  - Standard: USD 19.99/month
  - Pro: USD 39.99/month
- The remaining launch work is concentrated in:
  - applying the API usage-metering migration
  - provisioning/deploying the dedicated FastAPI Azure App Service
  - end-to-end API quota/revocation testing
  - resolving the automated Stripe price-catalog validation exception before live billing
  - production security/backup/monitoring hardening
  - live Stripe cutover

The product is test-mode billing capable, but it is not yet ready for public live billing/API launch.

## 1. Application and UX

- [x] Market Explorer visual system established.
- [x] Watchlist redesigned to match Market Explorer.
- [x] Portfolio expanded beyond the original minimal metrics.
- [x] History, Account, and Research Lab standardized.
- [x] Forecast, System Health, Advanced, and Plans pages standardized.
- [x] Account page refresh no longer intentionally falls back to Demo.
- [x] Custom domain working:
  - marketforecaster.oneeightaisystems.com
- [x] Demo / Standard / Pro entitlement model implemented.
- [x] Standard and Pro forecast export implemented.
- [x] Pro Research Lab entitlement implemented.
- [x] Pro API Access account panel implemented.

Status: COMPLETE for current launch scope.

## 2. Authentication and persistence

- [x] Supabase authentication integrated.
- [x] Persistent authenticated browser sessions implemented.
- [x] Browser stores only an opaque session handle.
- [x] Supabase tokens remain server-side.
- [x] Server-side refresh token encryption implemented.
- [x] Browser session is user-agent bound.
- [x] Logout revokes the persisted browser session.
- [x] Hard-refresh persistence user-tested successfully.
- [x] User data protected by Supabase RLS.
- [x] API-key tables explicitly denied to browser roles.

Remaining:
- [ ] Enable Supabase leaked-password protection.
- [ ] Re-run Supabase security advisor and confirm no unresolved launch-blocking warnings.

Status: FUNCTIONALLY COMPLETE; one security-hardening item remains.

## 3. Stripe subscriptions

Implemented:

- [x] Stripe-hosted full-page Checkout.
- [x] Standard recurring plan.
- [x] Pro recurring plan.
- [x] Signed Stripe webhook.
- [x] Webhook ordering / stale-event protection.
- [x] Checkout return-state synchronization.
- [x] Customer Portal support.
- [x] Cancel-at-period-end handling.
- [x] Duplicate active-subscription protection.
- [x] Existing Stripe Customer reuse.
- [x] Active plan changes routed through Stripe Customer Portal.
- [x] Standard sandbox checkout tested successfully.
- [x] Pro sandbox checkout tested successfully.
- [x] Cancellation / reactivation lifecycle tested.
- [x] Duplicate-subscription protection user-tested successfully.
- [x] Stripe Product Catalog contains active recurring Standard and Pro products.

Current sandbox prices:

- Standard: USD 19.99/month
- Pro: USD 39.99/month

Remaining:
- [ ] Resolve the automated Stripe recurring-price catalog validation exception.
- [ ] Do not treat this exception as resolved merely because the Stripe Dashboard products look correct.
- [ ] Re-run the no-charge catalog validator until both Standard and Pro pass.
- [ ] Keep billing mode in test until live-cutover checklist passes.
- [ ] At live cutover, create/configure live Price IDs and live webhook signing secret.
- [ ] Run one controlled live end-to-end acceptance transaction before public launch.

Status: SANDBOX FLOW COMPLETE; automated catalog validation and live cutover remain.

## 4. Stripe webhook / Supabase subscription authority

- [x] Subscription authority table implemented.
- [x] Webhook ordering metadata implemented.
- [x] Atomic subscription event RPC implemented.
- [x] Older Stripe snapshots cannot overwrite newer state.
- [x] checkout.session.completed cannot downgrade an already-active subscription.
- [x] Stripe webhook deployed as Supabase Edge Function.
- [x] Current webhook deployment uses signature verification and no Supabase JWT requirement.
- [x] Portal plan changes can map Standard/Pro from Stripe Price IDs.

Remaining:
- [ ] Confirm Stripe Standard/Pro Price IDs are configured in the Edge Function environment used for portal price mapping.
- [ ] Re-test Standard -> Pro and Pro -> Standard after any live Stripe Price-ID change.

Status: COMPLETE for sandbox; revalidate during live cutover.

## 5. Pro customer API keys

- [x] Customer API-key table implemented.
- [x] Plaintext key is shown once only.
- [x] Only SHA-256 key hash is persisted.
- [x] Maximum active keys per account implemented.
- [x] Individual key revocation implemented.
- [x] Every customer-key request rechecks current Pro subscription authority.
- [x] Standard/Demo customers cannot use customer API keys.
- [x] Customer API key rate limiting follows the key across source IPs.
- [x] API key management user-tested successfully.

Status: IMPLEMENTED; dedicated API host still required for real customer API use.

## 6. API monetization foundation

Merged in PR #47:

- [x] Account-wide monthly API usage design.
- [x] Configurable included monthly quota.
- [x] Initial launch allowance configured as 1,000 requests/month.
- [x] Quota is configuration, not hard-coded commercial pricing.
- [x] Atomic usage-consumption RPC defined.
- [x] API requests fail closed when usage metering is unavailable.
- [x] Quota exhaustion returns HTTP 429.
- [x] Usage response headers implemented:
  - X-Market-Forecaster-API-Limit
  - X-Market-Forecaster-API-Used
  - X-Market-Forecaster-API-Remaining
  - X-Market-Forecaster-API-Reset
- [x] Account -> API Access usage meter implemented.
- [x] API monetization roadmap documented.

Still required:
- [ ] Apply `20260928230000_api_usage_monthly.sql` to Supabase.
- [ ] Verify `public.api_usage_monthly` exists and browser roles cannot access it.
- [ ] Verify service-role-only `consume_market_forecaster_api_request` RPC.
- [ ] Verify production readiness sees API usage metering as configured.

Status: CODE COMPLETE; DATABASE ACTIVATION PENDING.

## 7. Dedicated FastAPI deployment

Implemented in repository:

- [x] Production FastAPI application.
- [x] /api/v1/health.
- [x] /api/v1/ready.
- [x] FastAPI customer-key authorization.
- [x] Uvicorn Azure startup command.
- [x] Manual GitHub workflow: Deploy Market Forecaster Pro API.
- [x] Workflow validates required server settings.
- [x] Workflow verifies health/readiness after deployment.
- [x] Workflow refuses to create Azure resources automatically.

Still required:

- [ ] Provision dedicated Azure Web App:
  - recommended name: marketforecaster-api
- [ ] Choose an appropriate low-cost initial App Service plan while retaining ability to scale.
- [ ] Configure:
  - MARKET_FORECASTER_ENV=production
  - MARKET_FORECASTER_API_KEY=<strong server-only secret>
  - MARKET_FORECASTER_ALLOWED_ORIGINS=https://marketforecaster.oneeightaisystems.com
  - MARKET_FORECASTER_ALLOW_CREDENTIALS=false
  - MARKET_FORECASTER_SUPABASE_URL=<project URL>
  - MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY=<server-only secret>
  - SUBSCRIPTIONS_ENABLED=true
  - MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS=1000
  - MARKET_FORECASTER_SHARED_RATE_LIMIT_ENABLED=true
  - MARKET_FORECASTER_RATE_LIMIT_REQUESTS=30
  - MARKET_FORECASTER_RATE_LIMIT_WINDOW_SECONDS=60
  - MARKET_FORECASTER_RATE_LIMIT_HASH_SECRET=<strong server-only secret>
- [ ] Run the manual API deployment workflow.
- [ ] Verify /api/v1/health.
- [ ] Verify /api/v1/ready.
- [ ] Set on Streamlit UI:
  - MARKET_FORECASTER_API_PUBLIC_URL=https://<api-host>
  - MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS=1000
- [ ] Consider custom API hostname later:
  - api.marketforecaster.oneeightaisystems.com

Status: DEPLOYMENT WORKFLOW READY; AZURE RESOURCE NOT YET PROVISIONED.

## 8. Required API acceptance tests

After the usage migration and API host are live:

- [ ] Create a Pro customer API key.
- [ ] Call one protected endpoint using X-API-Key.
- [ ] Confirm HTTP 200.
- [ ] Confirm API usage changes from 0 to 1.
- [ ] Confirm response reports the correct limit / used / remaining / reset values.
- [ ] Confirm Account -> API Access shows the same usage count.
- [ ] Revoke the key.
- [ ] Confirm the same request returns HTTP 401.
- [ ] Temporarily lower sandbox/test quota to 3 requests.
- [ ] Confirm request 1 succeeds.
- [ ] Confirm request 2 succeeds.
- [ ] Confirm request 3 succeeds.
- [ ] Confirm request 4 returns HTTP 429.
- [ ] Restore quota to 1,000.
- [ ] Verify usage remains account-wide even when multiple API keys are created.
- [ ] Verify Standard plan cannot authorize API requests.

Status: PENDING dedicated API deployment.

## 9. Production data / backup readiness

- [x] User data stored in Supabase Postgres.
- [x] Subscription authority stored in Supabase.
- [x] Forecast contracts / shared authority architecture implemented.

Still required before public paid launch:

- [ ] Confirm Supabase backup/PITR capability for the selected plan.
- [ ] Document restore owner and recovery procedure.
- [ ] Perform at least one non-production restore drill.
- [ ] Document expected recovery time and recovery point objectives.

Status: PENDING.

## 10. Monitoring and operations

Existing:

- [x] GitHub compile/lint/unit/container CI.
- [x] Azure Streamlit deployment smoke test.
- [x] API health/readiness endpoints.
- [x] Structured request IDs/access logs.
- [x] Shared API rate-limit implementation.
- [x] Demo cache readiness checks.

Still recommended:

- [ ] Azure 5xx-rate alert.
- [ ] API response-latency alert.
- [ ] CPU alert.
- [ ] Memory alert.
- [ ] App restart/container-start-failure alert.
- [ ] Failed-deployment notification.
- [ ] API quota exhaustion visibility.
- [ ] Subscription webhook failure visibility.
- [ ] Optional later: Azure Front Door / WAF / API Management when API traffic justifies it.

Status: CORE OBSERVABILITY EXISTS; ALERTING PENDING.

## 11. Demo and forecast authority

- [x] Shared Forecast Contract architecture.
- [x] Shared Forecast Authority architecture.
- [x] Demo cache / fallback mechanism.
- [x] Scheduled Demo contract refresh workflow.
- [x] Secretless GitHub OIDC publisher architecture.
- [x] Production readiness gate checks Demo contract availability.

Before final launch:

- [ ] Run shared Demo refresh manually once.
- [ ] Confirm all 14 Demo contracts exist and are READY.
- [ ] Confirm shared-store outage falls back to deployment-local contracts.

Status: IMPLEMENTED; final launch verification remains.

## 12. Latest repository status

- [x] PR #36 — persistent browser authentication.
- [x] PR #37 — History / Account / Research Lab UI consistency.
- [x] PR #38 — remaining Market Explorer UI consistency.
- [x] PR #39 — Azure deployment preflight.
- [x] PR #40 — Stripe activation and catalog-readiness checks.
- [x] PR #41 — order-safe Stripe webhook updates.
- [x] PR #42 — checkout return and billing sync UX.
- [x] PR #43 — Standard/Pro canonical forecast exports.
- [x] PR #44 — revocable Pro API keys.
- [x] PR #45 — dedicated Pro API Azure deployment workflow.
- [x] PR #46 — Stripe lifecycle hardening / duplicate subscription protection.
- [x] PR #47 — monetizable API usage metering and monthly quotas.
- [x] PR #47 CI passed before merge.
- [ ] Verify the latest master commit containing PR #47 has completed production deployment.

Status: SOURCE CODE CURRENT; latest production deployment confirmation still required.

## 13. Final launch-blocker checklist

The project should not be called production-complete until every item below is checked:

- [ ] API usage-metering migration applied.
- [ ] Dedicated Azure FastAPI host provisioned.
- [ ] Dedicated API deployment passes /health and /ready.
- [ ] Customer API usage count tested end-to-end.
- [ ] API key revocation tested against live API host.
- [ ] Quota exhaustion tested.
- [ ] Automated Stripe Standard/Pro recurring-price catalog validator passes.
- [ ] Supabase leaked-password protection addressed.
- [ ] Backup/PITR plan confirmed.
- [ ] Restore drill completed.
- [ ] Core Azure operational alerts configured.
- [ ] Demo contract refresh / fallback launch check completed.
- [ ] Production readiness --strict passes.
- [ ] Production readiness --strict --require-billing passes.
- [ ] Live Stripe products/prices/webhook configured.
- [ ] Live billing-mode safety check passes.
- [ ] Controlled live subscription acceptance succeeds.
- [ ] Final custom-domain / TLS / sign-in / sign-out / Standard / Pro regression pass succeeds.

## 14. Post-launch API revenue roadmap

Not required to finish the initial launch:

- [ ] Collect API requests/customer/month.
- [ ] Measure endpoint mix.
- [ ] Measure p50/p95 latency.
- [ ] Estimate infrastructure/model cost per API request.
- [ ] Measure percentage of Pro users creating API keys.
- [ ] Measure quota exhaustion rate.
- [ ] Decide whether to introduce:
  - Pro API Growth add-on
  - API Business tier
  - API-only subscription
  - metered overage
- [ ] Add Stripe usage-based billing only after actual cost/usage economics are known.

## Next three priorities

1. Apply and validate the API usage-metering Supabase migration.
2. Provision and deploy the dedicated Azure FastAPI host.
3. Run the full Pro API acceptance suite, then close the Stripe catalog validation issue before live billing cutover.
