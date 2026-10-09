# Market Forecaster — Project Status Runbook

Status date: 2026-10-09 (America/Chicago)

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
  - production security / backup hardening
  - activating and operating the encrypted Supabase logical-backup workflow
  - completing a non-production restore drill
  - provider-side leaked-password protection / Supabase plan decision
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

Completed compensating control:
- [x] Market Forecaster now requires at least 12 characters plus uppercase,
  lowercase, numeric, and symbol characters for new passwords created through
  the application.

Remaining:
- [ ] Decide whether to upgrade Supabase from Free to a plan that includes
  leaked-password protection.
- [ ] Re-run Supabase security advisor after that decision. The current advisor
  warning is the Free-plan leaked-password-protection limitation.

Status: FUNCTIONALLY COMPLETE; PROVIDER-SIDE PASSWORD BREACH CHECK REMAINS PLAN-DEPENDENT.

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

Completed:
- [x] Automated no-charge Stripe recurring-price catalog validation passes for
  both Standard and Pro in the strict production-readiness gate.

Remaining:
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

Status: IMPLEMENTED; dedicated API host is now provisioned and deployed.

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

Completed activation:
- [x] Applied `20260928230000_api_usage_monthly.sql` to Supabase.
- [x] Verified `public.api_usage_monthly` exists with RLS enabled.
- [x] Verified browser roles have no table grants.
- [x] Verified `consume_market_forecaster_api_request` is executable by
  `service_role` and not by `anon` or `authenticated`.

Completed host validation:
- [x] Dedicated API deployment reports customer API-key authorization configured.
- [x] Dedicated API deployment reports API usage metering configured.
- [x] Monthly Pro API allowance verified at 1,000 requests.

Status: CODE + DATABASE + HOST VALIDATION COMPLETE.

## 7. Dedicated FastAPI deployment

Implemented in repository:

- [x] Production FastAPI application.
- [x] /api/v1/health.
- [x] /api/v1/ready.
- [x] FastAPI customer-key authorization.
- [x] Customer/internal API authorization boundaries implemented.
- [x] Internal governance/operations routes reserved for trusted server key.
- [x] Internal-only routes hidden from public OpenAPI schema.
- [x] Customer `GET /api/v1/api/usage` endpoint implemented.
- [x] Uvicorn Azure startup command.
- [x] Manual GitHub workflow: Deploy Market Forecaster Pro API.
- [x] Workflow validates required server settings.
- [x] Workflow verifies health/readiness after deployment.
- [x] Workflow refuses to create Azure resources automatically.

Completed:

- [x] Provisioned dedicated Azure Web App:
  - name: marketforecaster-api
  - host: marketforecaster-api.azurewebsites.net
- [x] Reused existing App Service plan `ASP-OneEightAISystems-a62e` to avoid a second paid compute plan.
- [x] Configure:
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
- [x] Run the manual API deployment workflow.
- [x] Verify /api/v1/health.
- [x] Verify /api/v1/ready.
- [x] Streamlit deployment now persists:
  - MARKET_FORECASTER_API_PUBLIC_URL=https://marketforecaster-api.azurewebsites.net
  - MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS=1000
- [ ] Consider custom API hostname later:
  - api.marketforecaster.oneeightaisystems.com

Status: DEDICATED API HOST PROVISIONED, DEPLOYED, HEALTHY, AND METERING-READY.

## 8. Required API acceptance tests

Completed live API acceptance:

- [x] Create a Pro customer API key.
- [x] Call a protected endpoint using X-API-Key.
- [x] Confirm HTTP 200.
- [x] Confirm API usage changes from 0 to 1.
- [x] Confirm response reports the correct limit / used / remaining / reset values.
- [x] Revoke the key.
- [x] Confirm the same request is rejected as an invalid/inactive API key.
- [x] Confirm rejected revoked-key request does not consume quota.
- [x] Temporarily lower sandbox/test quota to 3 requests.
- [x] Confirm allowed requests increment usage to the configured limit.
- [x] Confirm the next request returns HTTP 429 with monthly quota exceeded.
- [x] Verify usage remains account-wide across multiple API keys. The second key inherited the first key's account usage count.
- [x] Fix and permanently migrate the live `period_start` ambiguity discovered in the usage RPC.

Remaining:
- [ ] Confirm Account -> API Access displays the same current usage count after the latest deployment.
- [x] API launch quota reconciled back to 1,000 and verified through `/api/v1/ready`.
- [x] Automated Standard-plan API denial regression confirms an active Standard
  subscription cannot authorize a customer API key and denial occurs before
  monthly usage is consumed.
- [ ] Optional live Standard-account API denial check deferred because the
  current subscription table contains only active Pro test accounts; do not
  downgrade either active Pro account solely for this test.

Status: CORE PRO API ACCEPTANCE PASSED; STANDARD DENIAL IS AUTOMATED AND LIVE TEST IS DEFERRED SAFELY.

## 9. Production data / backup readiness

- [x] User data stored in Supabase Postgres.
- [x] Subscription authority stored in Supabase.
- [x] Forecast contracts / shared authority architecture implemented.

Completed backup design:
- [x] Confirmed current Supabase Free-plan posture requires an application-owned
  logical backup process rather than relying on paid-plan daily backups.
- [x] Encrypted daily Supabase CLI logical-backup workflow implemented.
- [x] Backup includes roles, schema, data, migration history, and supported Auth
  database data.
- [x] Backup generates SHA-256 checksums and removes plaintext before artifact upload.
- [x] 30-day encrypted GitHub artifact retention configured.
- [x] Restore owner and recovery procedure documented in `SUPABASE_BACKUP_RESTORE.md`.
- [x] Initial operating targets documented: RPO <= 24 hours and target RTO 4 hours
  until measured by a full restore drill.
- [x] Manual restore/integrity workflow implemented with explicit production-project protection.

Still required before public paid launch:
- [ ] Configure `MARKET_FORECASTER_SUPABASE_DB_URL` repository secret.
- [ ] Configure `MARKET_FORECASTER_BACKUP_PASSPHRASE` and retain an external recovery copy.
- [ ] Run the first encrypted production logical backup.
- [ ] Run integrity-only restore validation against that backup artifact.
- [ ] Configure a disposable/non-production restore database and
  `MARKET_FORECASTER_SUPABASE_RESTORE_DB_URL`.
- [ ] Perform one full non-production restore drill and record measured RTO.
- [ ] Decide whether to upgrade Supabase before public paid launch for provider-managed daily backups and leaked-password protection.

Status: BACKUP/RESTORE AUTOMATION IMPLEMENTED; SECRET ACTIVATION + FULL RESTORE DRILL PENDING.

## 10. Monitoring and operations

Existing:

- [x] GitHub compile/lint/unit/container CI.
- [x] Azure Streamlit deployment smoke test.
- [x] API health/readiness endpoints.
- [x] Structured request IDs/access logs.
- [x] Shared API rate-limit implementation.
- [x] Demo cache readiness checks.

Still recommended:

- [x] Hourly secretless GitHub production smoke monitor for the custom-domain UI and dedicated API health/readiness.
- [x] Hourly verification of Pro customer-key authorization, usage metering, 1,000-request allowance, and shared API rate limiting.
- [x] Azure Monitor alert workflow prepared and validated without creating billable alert resources automatically.
- [x] Azure email action group activated and verified.
- [x] Six Azure Monitor metric alerts created and enabled.
- [x] Azure UI/API 5xx alerts active.
- [x] UI/API response-latency alerts active.
- [x] App Service CPU alert active.
- [x] App Service memory alert active.
- [ ] App restart/container-start-failure alert.
- [ ] Failed-deployment notification.
- [ ] API quota exhaustion visibility.
- [ ] Subscription webhook failure visibility.
- [ ] Optional later: Azure Front Door / WAF / API Management when API traffic justifies it.

Status: CORE OBSERVABILITY + HOURLY PUBLIC SMOKE MONITOR + AZURE METRIC/EMAIL ALERTING ACTIVE.

## 11. Demo and forecast authority

- [x] Shared Forecast Contract architecture.
- [x] Shared Forecast Authority architecture.
- [x] Demo cache / fallback mechanism.
- [x] Scheduled Demo contract refresh workflow.
- [x] Secretless GitHub OIDC publisher architecture.
- [x] Production readiness gate checks Demo contract availability.

Before final launch:

- [x] Scheduled shared Demo refresh completed successfully.
- [x] Confirmed all 14 Demo contracts exist and are READY in Supabase.
- [x] Automated shared-store outage regression confirms fallback to deployment-local contracts.
- [ ] Optional destructive live-outage simulation intentionally not performed against production.

Status: DEMO CONTRACT AVAILABILITY + FALLBACK REGRESSION VERIFIED.

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
- [x] Latest launch-readiness master deployment completed successfully.
- [x] Strict post-deploy billing/catalog readiness passed.
- [x] Dedicated API readiness verified at the 1,000-request launch allowance.
- [x] Hourly production monitor merged and first run passed.

Status: SOURCE CODE + PRODUCTION DEPLOYMENT CURRENT.

## 13. Final launch-blocker checklist

The project should not be called production-complete until every item below is checked:

- [x] API usage-metering migration applied.
- [x] Dedicated Azure FastAPI host provisioned.
- [x] Dedicated API deployment passes /health and /ready.
- [x] Customer API usage count tested end-to-end.
- [x] API key revocation tested against live API host.
- [x] Quota exhaustion tested.
- [x] Automated Stripe Standard/Pro recurring-price catalog validator passes in the strict post-deploy gate.
- [ ] Supabase leaked-password protection decision addressed. Current Supabase organization is on the Free plan; leaked-password protection is available on Pro and above, so enabling it requires a plan upgrade.
- [x] Backup plan selected for current Free-plan stage: encrypted daily off-platform logical backup with documented restore procedure.
- [x] First encrypted production logical backup completed successfully (workflow run 37965746226).
- [x] Integrity-only restore validation completed successfully (workflow run 37967481245): decryption passed and all SHA-256 checksums passed.
- [ ] Full non-production restore drill completed.
- [x] Core Azure operational alerts activated and verified.
- [x] Demo contract refresh / fallback launch check completed through live contract verification plus automated fallback regression.
- [x] Automated post-deploy production readiness --strict passes.
- [x] Automated post-deploy production readiness --strict --require-billing passes.
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

1. Perform a full non-production restore drill when a disposable Supabase target is available; the encrypted backup and integrity-validation stages now pass.
2. Decide whether to upgrade Supabase for provider-managed backups and leaked-password protection before public paid launch.
3. Complete the live Stripe cutover checklist and one controlled real subscription acceptance transaction.
