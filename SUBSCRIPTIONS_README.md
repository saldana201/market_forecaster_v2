# Market Forecaster 4.1.3 — Subscriptions

4.1.3 establishes Stripe-backed Standard and Pro subscription authority.

## Feature flag

Billing stays dormant until explicitly enabled:

    SUBSCRIPTIONS_ENABLED=true

When it is false, authenticated accounts continue using the existing 4.1.2 Standard behavior.

When it is true, paid feature access is resolved from `public.subscriptions`.

## Azure App Service settings

Keep the existing Supabase settings and add:

    MARKET_FORECASTER_PUBLIC_URL=https://marketforecaster.oneeightaisystems.com
    STRIPE_SECRET_KEY=sk_live_...              # use sk_test_... during testing
    STRIPE_STANDARD_PRICE_ID=price_...
    STRIPE_PRO_PRICE_ID=price_...
    SUBSCRIPTIONS_ENABLED=true

Never commit Stripe secret keys to GitHub.

## Supabase Edge Function

The Stripe webhook is checked in at:

    supabase/functions/stripe-webhook

Configure `STRIPE_WEBHOOK_SECRET` in Supabase, deploy with `--no-verify-jwt`, and
register the deployed HTTPS URL as a Stripe webhook/event destination.

The function verifies Stripe's signature before using the service role to update
subscription authority.

## Access model

- Demo: anonymous, session-only.
- Authenticated account while billing is disabled: existing Standard behavior.
- Billing enabled + active/trialing/past_due Standard: Standard entitlements.
- Billing enabled + active/trialing/past_due Pro: Pro entitlements.
- Billing enabled + no valid subscription: Demo entitlements, even if signed in.
- Browser users can SELECT only their own subscription row; they cannot write plan/status.

## Checkout

The app uses Stripe-hosted Checkout and Customer Portal. Card details are never collected
or stored by Market Forecaster.
