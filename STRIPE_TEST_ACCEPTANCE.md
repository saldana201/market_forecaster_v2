# Stripe Test-Mode Acceptance — Market Forecaster

Use this checklist after the Stripe readiness changes are merged and deployed.

## 1. Azure App Service

Keep paid access disabled while configuration is being validated:

    SUBSCRIPTIONS_ENABLED=false
    MARKET_FORECASTER_BILLING_MODE=test
    MARKET_FORECASTER_PUBLIC_URL=https://marketforecaster.oneeightaisystems.com
    STRIPE_SECRET_KEY=sk_test_...
    STRIPE_STANDARD_PRICE_ID=price_...
    STRIPE_PRO_PRICE_ID=price_...

Do not use live Stripe credentials during this phase.

## 2. Supabase

Apply:

    supabase/migrations/20260927091000_subscription_webhook_ordering.sql

Then deploy:

    supabase functions deploy stripe-webhook --no-verify-jwt

The Edge Function must have:

    STRIPE_WEBHOOK_SECRET=whsec_...

The function uses Supabase-provided `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY`.

## 3. Stripe test event destination

Register the deployed `stripe-webhook` HTTPS endpoint for:

- checkout.session.completed
- customer.subscription.created
- customer.subscription.updated
- customer.subscription.deleted

Use the signing secret from that exact test-mode event destination as
`STRIPE_WEBHOOK_SECRET`.

## 4. No-charge validation

Sign in to Market Forecaster and open Account → Membership & billing.

Open **Billing activation checklist** and run:

**Validate Stripe recurring prices (no charge)**

Both Standard and Pro must pass. This validation reads Price metadata only and
does not create a Checkout Session, customer, subscription, invoice, or charge.

Also run:

    python -m market_forecaster.scripts.production_readiness --strict --require-billing

For this command, the deployment environment must contain the same test-mode
billing settings.

## 5. Enable test-mode subscriptions

Only after the configuration and catalog checks pass:

    SUBSCRIPTIONS_ENABLED=true

Redeploy. The Azure preflight will reject a test/live key mismatch.

## 6. Standard acceptance test

1. Create or use a dedicated test account.
2. Select Standard.
3. Start Stripe Checkout.
4. Use a Stripe test payment method.
5. Complete Checkout and return to Market Forecaster.
6. Confirm the account resolves to Standard.
7. Confirm Watchlist, Portfolio, and Forecast History remain available.
8. Confirm Research Lab remains locked if Standard does not include it.
9. Confirm `public.subscriptions` contains the test account with:
   - plan = standard
   - status = active or trialing
   - Stripe customer/subscription IDs populated
   - Stripe event metadata populated
10. Refresh the browser and confirm the subscription state remains correct.

## 7. Pro acceptance test

Repeat with Pro and confirm:

- plan = pro
- status = active or trialing
- Research Lab is accessible
- Pro-only diagnostics/API entitlements resolve correctly after refresh

## 8. Webhook ordering test

Stripe may retry or reorder events. Verify that:

- duplicate events do not create duplicate subscription rows
- an older subscription event cannot overwrite a newer one
- checkout.session.completed cannot downgrade an already active subscription
- cancel-at-period-end changes are reflected without immediately removing paid access
- customer.subscription.deleted resolves the account back to Demo entitlements

## 9. Customer Portal test

For an account with a Stripe customer ID:

1. Open the billing portal.
2. Change/cancel the test subscription.
3. Return to Market Forecaster.
4. Confirm webhook synchronization updates plan/status correctly.

## 10. Live cutover

Do not switch to live mode until all test-mode acceptance checks pass.

At cutover, change these together:

    MARKET_FORECASTER_BILLING_MODE=live
    STRIPE_SECRET_KEY=sk_live_...
    STRIPE_STANDARD_PRICE_ID=<live Standard price>
    STRIPE_PRO_PRICE_ID=<live Pro price>
    STRIPE_WEBHOOK_SECRET=<live event destination signing secret>

Keep `MARKET_FORECASTER_PUBLIC_URL` on HTTPS.

Run the strict billing readiness gate again before accepting live customers.
