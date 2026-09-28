# Stripe subscription webhook

This Edge Function is the trusted writer for `public.subscriptions`.

## Required Edge Function configuration

Set these in Supabase Edge Function secrets/environment before registering the endpoint with Stripe:

    STRIPE_WEBHOOK_SECRET=whsec_...
    STRIPE_STANDARD_PRICE_ID=price_...
    STRIPE_PRO_PRICE_ID=price_...

The two Price IDs are not sensitive, but keeping the mapping beside the webhook lets
`customer.subscription.updated` resolve Standard vs Pro when a customer changes plans
through Stripe Customer Portal. Price mapping takes precedence over stale subscription
metadata.

Supabase provides `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` to deployed Edge Functions.

## Database migration

Apply the subscription webhook ordering migration before deploying this function:

    supabase/migrations/20260927091000_subscription_webhook_ordering.sql

It adds the last-applied Stripe event metadata to `public.subscriptions` and a
service-role-only RPC that rejects older subscription snapshots. Stripe does not
guarantee webhook delivery order, so this prevents an older event from overwriting
a newer subscription state.

## Deploy

Deploy with JWT verification disabled because Stripe does not send a Supabase JWT.
The function performs its own authentication by verifying the `Stripe-Signature`
HMAC against `STRIPE_WEBHOOK_SECRET`.

    supabase functions deploy stripe-webhook --no-verify-jwt

## Stripe event destination

Register the deployed HTTPS function URL for these snapshot events:

- checkout.session.completed
- customer.subscription.created
- customer.subscription.updated
- customer.subscription.deleted

The Checkout Session and Subscription metadata must contain:

- user_id — Supabase Auth UUID
- plan — standard or pro

Market Forecaster's checkout creator adds both automatically.

For Customer Portal plan changes, the webhook derives the plan from the configured
Standard/Pro Stripe Price IDs because Stripe preserves existing subscription metadata
when the subscription item is changed.

## Event ordering and retries

Stripe can retry events and can deliver related events out of order.

Market Forecaster treats `customer.subscription.*` snapshots as the authority for
subscription status. Each authoritative event stores its Stripe event ID, event type,
and Stripe-created timestamp. Older snapshots are acknowledged but ignored.

`checkout.session.completed` links the Stripe customer/subscription identifiers but
does not downgrade a subscription status that was already applied by a subscription
event. This specifically protects the case where `customer.subscription.created`
arrives before `checkout.session.completed`.

Duplicate delivery of the latest event is safe and idempotent.

## Security

Do not place the Stripe webhook signing secret or Stripe secret API key in browser code.
Subscription rows are read-only to authenticated users and writable only through trusted
service-role/backend code.
