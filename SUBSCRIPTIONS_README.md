# Market Forecaster 4.1.3 — Subscriptions

4.1.3 establishes Stripe-backed Standard and Pro subscription authority.

## Feature flag

Billing stays dormant until explicitly enabled:

    SUBSCRIPTIONS_ENABLED=true

When it is false, authenticated accounts continue using the existing 4.1.2 Standard behavior.

When it is true, paid feature access is resolved from `public.subscriptions`.

## Azure App Service settings

Keep the existing Supabase settings and add:

    MARKET_FORECASTER_BILLING_MODE=test       # switch to live only at production cutover
    MARKET_FORECASTER_PUBLIC_URL=https://marketforecaster.oneeightaisystems.com
    STRIPE_SECRET_KEY=sk_test_...              # use sk_live_... only with billing mode=live
    STRIPE_STANDARD_PRICE_ID=price_...
    STRIPE_PRO_PRICE_ID=price_...
    SUBSCRIPTIONS_ENABLED=true

Never commit Stripe secret keys to GitHub.

Billing mode is an explicit safety boundary:

- `MARKET_FORECASTER_BILLING_MODE=test` requires an `sk_test_` Stripe key.
- `MARKET_FORECASTER_BILLING_MODE=live` requires an `sk_live_` Stripe key.
- live mode also requires an HTTPS public return URL.
- a mode/key mismatch blocks Checkout and blocks the Azure production deployment when subscriptions are enabled.

This is designed to prevent a test activation from accidentally using live Stripe credentials.

## Supabase Edge Function

The Stripe webhook is checked in at:

    supabase/functions/stripe-webhook

Configure the webhook secret plus the Standard/Pro Price IDs in Supabase, deploy
with `--no-verify-jwt`, and register the deployed HTTPS URL as a Stripe
webhook/event destination:

    STRIPE_WEBHOOK_SECRET=whsec_...
    STRIPE_STANDARD_PRICE_ID=price_...
    STRIPE_PRO_PRICE_ID=price_...

The function verifies Stripe's signature before using the service role to update
subscription authority. Price IDs are also used to resolve portal-driven plan
changes so a stale subscription metadata value cannot keep the wrong Market
Forecaster tier.

## Access model

- Demo: anonymous, session-only.
- Authenticated account while billing is disabled: existing Standard behavior.
- Billing enabled + active/trialing/past_due Standard: Standard entitlements.
- Billing enabled + active/trialing/past_due Pro: Pro entitlements.
- Billing enabled + no valid subscription: Demo entitlements, even if signed in.
- Browser users can SELECT only their own subscription row; they cannot write plan/status.

## Checkout and plan changes

The app uses Stripe-hosted Checkout and Customer Portal. Card details are never
collected or stored by Market Forecaster.

Checkout is only used when the account does not already have an entitled paid
subscription. If an active Standard or Pro subscription exists, Market Forecaster
routes plan changes through Stripe Customer Portal instead of creating a second
recurring subscription.

When a previously canceled account subscribes again, Market Forecaster reuses the
existing Stripe Customer ID when available instead of creating another customer.


## Activation diagnostics

The signed-in Subscription panel exposes a secret-safe activation checklist showing:

- subscription feature flag
- persistent account storage
- explicit billing mode
- Stripe secret-key presence and test/live mode match
- Standard recurring-price configuration
- Pro recurring-price configuration
- public return URL

The checklist never displays secret keys or full Stripe credentials.

It also provides **Validate Stripe recurring prices (no charge)**. That check reads
the configured Standard and Pro Stripe Price objects and verifies that they are:

- in the same test/live environment as the configured billing mode
- active
- recurring
- configured with a positive amount and currency

The validation does not create a Checkout Session, customer, subscription, invoice,
or charge.

Recommended activation sequence:

1. Set `MARKET_FORECASTER_BILLING_MODE=test`.
2. Configure the `sk_test_` secret and test Standard/Pro recurring Price IDs.
3. Leave `SUBSCRIPTIONS_ENABLED=false` while reviewing the activation checklist.
4. Run the no-charge Stripe price validation.
5. Configure and test the signed Stripe webhook.
6. Set `SUBSCRIPTIONS_ENABLED=true` for end-to-end test-mode Checkout acceptance.
7. Only after test acceptance, change billing mode and credentials to live together.
