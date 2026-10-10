# Stripe Live Cutover — Market Forecaster

This runbook is the controlled switch from Stripe test mode to real customer billing.

## 1. Stripe account / business readiness

Before changing application settings:

- Stripe account verification is complete.
- Business legal name and tax information are accepted.
- Payout bank account is configured.
- Live payments are enabled.
- Customer-facing business name / statement descriptor is appropriate.

## 2. Create live recurring prices

In Stripe **Live mode**, create or confirm:

- Market Forecaster Standard — USD 19.99/month, recurring monthly.
- Market Forecaster Pro — USD 39.99/month, recurring monthly.

Save the two live Price IDs:

- live Standard Price ID
- live Pro Price ID

Do not reuse test-mode Price IDs.

## 3. Configure live Customer Portal

Stripe test-mode and live-mode objects/configuration are separate. In live mode,
confirm the Customer Portal allows customers to:

- manage payment methods
- cancel at period end
- reactivate before period end when supported
- move between the live Standard and Pro recurring products/prices

Market Forecaster blocks a second Checkout while an entitled paid subscription
already exists. Existing paid customers should change plans through the Portal.

## 4. Create live webhook destination

Create a **live-mode** Stripe event destination for:

    https://pbttpkbkimqdoilmwryi.supabase.co/functions/v1/stripe-webhook

Subscribe to:

- checkout.session.completed
- customer.subscription.created
- customer.subscription.updated
- customer.subscription.deleted

Copy the signing secret from this exact live destination.

The live signing secret is different from the test-mode signing secret.

## 5. Switch the Supabase Edge Function mapping

Update the deployed `stripe-webhook` Edge Function environment together:

    STRIPE_WEBHOOK_SECRET=<live webhook signing secret>
    STRIPE_STANDARD_PRICE_ID=<live Standard Price ID>
    STRIPE_PRO_PRICE_ID=<live Pro Price ID>

The function does not need the Stripe account secret key. It verifies Stripe
signatures and maps the live Price IDs back to Market Forecaster plans.

After the environment values are updated, redeploy:

    supabase functions deploy stripe-webhook --no-verify-jwt

At this point, the webhook is authoritative for **live** Stripe events. The old
test-mode destination will no longer validate against the live signing secret.

## 6. Switch Azure App Service billing settings

Update the Market Forecaster App Service settings together:

    MARKET_FORECASTER_BILLING_MODE=live
    STRIPE_SECRET_KEY=sk_live_...
    STRIPE_STANDARD_PRICE_ID=<live Standard Price ID>
    STRIPE_PRO_PRICE_ID=<live Pro Price ID>
    MARKET_FORECASTER_PUBLIC_URL=https://marketforecaster.oneeightaisystems.com
    SUBSCRIPTIONS_ENABLED=true

Do not mix a live secret key with test Price IDs or a test secret key with live
Price IDs.

Market Forecaster's deployment preflight blocks a billing-mode/key mismatch.

## 7. No-charge live validation

Before entering a real card:

1. Run GitHub Actions workflow:
   **Validate Stripe live cutover**
2. It must pass:
   - live billing-mode safety boundary
   - live `sk_live_` key check
   - HTTPS return URL check
   - Standard live recurring-price validation
   - Pro live recurring-price validation
   - strict `production_readiness --strict --require-billing`
   - public application health
3. Save the generated readiness artifact.

This workflow reads Stripe catalog metadata only and does not create a customer,
subscription, invoice, or charge.

## 8. Controlled real-money acceptance

Use a dedicated Market Forecaster account that is not carrying an existing test
subscription.

Recommended first live transaction:

1. Sign in at the public custom domain.
2. Select **Standard**.
3. Complete Stripe-hosted Checkout with a real payment method.
4. Return to Market Forecaster.
5. Confirm the account becomes Standard only after webhook-backed subscription
   authority is present.
6. Refresh the browser and confirm Standard persists.
7. Verify in Supabase:
   - plan = standard
   - status = active or trialing
   - live Stripe customer ID populated
   - live Stripe subscription ID populated
   - Stripe event metadata populated
8. Open Customer Portal and confirm it loads for the same live customer.
9. Confirm duplicate Checkout is blocked while the subscription is entitled.

After this validation, cancel the acceptance subscription if it is not intended
to remain active. Handle any refund separately in Stripe according to the desired
accounting treatment.

## 9. Pro live acceptance

The live Pro Price is already validated by the no-charge catalog check.

Before broad launch, confirm Pro entitlement behavior using one of:

- a controlled live Pro subscription, or
- a controlled Standard-to-Pro Portal change using the acceptance account.

Verify:

- plan resolves to pro
- Research Lab unlocks
- Pro API-key creation is allowed
- existing API quota/readiness remains healthy
- no second active recurring subscription is created

## 10. Final regression

After the live transaction:

- custom domain and TLS work
- sign-up works
- sign-in works
- hard refresh preserves authenticated session
- sign-out returns to Demo
- Demo remains usable
- Standard entitlement works
- Pro entitlement works
- Customer Portal works
- webhook updates arrive
- API health/readiness passes
- hourly production monitor passes
- Azure alerts remain enabled
- latest encrypted backup succeeds

## 11. Rollback

If live validation fails before a real transaction:

- set `MARKET_FORECASTER_BILLING_MODE=test`
- restore the test Stripe secret and test Price IDs in Azure
- restore the test webhook signing secret and test Price IDs in Supabase
- redeploy the Edge Function
- rerun strict readiness

If a live customer has already paid, do not silently revert subscription authority.
Resolve the customer charge/subscription in Stripe first, then coordinate the
application rollback.

## Secrets

Never paste any of the following into chat, issues, screenshots, source control,
or documentation:

- `sk_live_...`
- webhook signing secrets
- Supabase service-role key
- database passwords
- business tax identifiers
