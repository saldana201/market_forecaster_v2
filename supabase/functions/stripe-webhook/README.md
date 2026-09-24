# Stripe subscription webhook

This Edge Function is the trusted writer for `public.subscriptions`.

## Required secret

Set this in Supabase Edge Function secrets before registering the endpoint with Stripe:

    STRIPE_WEBHOOK_SECRET=whsec_...

Supabase provides `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` to deployed Edge Functions.

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

## Security

Do not place the Stripe webhook signing secret or Stripe secret API key in browser code.
Subscription rows are read-only to authenticated users and writable only through trusted
service-role/backend code.
