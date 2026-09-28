import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const encoder = new TextEncoder();
const ALLOWED_STATUSES = new Set([
  "none",
  "trialing",
  "active",
  "past_due",
  "unpaid",
  "canceled",
  "incomplete",
  "incomplete_expired",
  "paused",
]);
const ALLOWED_PLANS = new Set(["demo", "standard", "pro"]);
const PAID_PLANS = new Set(["standard", "pro"]);

function hex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

async function verifyStripeSignature(
  rawBody: string,
  signatureHeader: string,
  secret: string,
  toleranceSeconds = 300,
): Promise<boolean> {
  const parts = signatureHeader.split(",");
  const timestamp = parts
    .find((part) => part.startsWith("t="))
    ?.slice(2);
  const signatures = parts
    .filter((part) => part.startsWith("v1="))
    .map((part) => part.slice(3));

  if (!timestamp || signatures.length === 0) return false;

  const ts = Number(timestamp);
  if (!Number.isFinite(ts)) return false;
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - ts) > toleranceSeconds) return false;

  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = await crypto.subtle.sign(
    "HMAC",
    key,
    encoder.encode(`${timestamp}.${rawBody}`),
  );
  const expected = hex(digest);
  return signatures.some((candidate) => timingSafeEqual(candidate, expected));
}

function normalizePlan(value: unknown): string {
  const plan = String(value || "demo").toLowerCase();
  return ALLOWED_PLANS.has(plan) ? plan : "demo";
}

function normalizeStatus(value: unknown): string {
  const status = String(value || "none").toLowerCase();
  return ALLOWED_STATUSES.has(status) ? status : "none";
}

function planFromPriceId(value: unknown): string | null {
  const priceId = String(value || "").trim();
  if (!priceId) return null;

  const standardPrice = String(
    Deno.env.get("STRIPE_STANDARD_PRICE_ID") || "",
  ).trim();
  const proPrice = String(
    Deno.env.get("STRIPE_PRO_PRICE_ID") || "",
  ).trim();

  if (standardPrice && priceId === standardPrice) return "standard";
  if (proPrice && priceId === proPrice) return "pro";
  return null;
}

function isoFromUnix(value: unknown): string | null {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return null;
  return new Date(seconds * 1000).toISOString();
}

function stripeId(value: unknown): string | null {
  if (typeof value === "string") {
    const normalized = value.trim();
    return normalized || null;
  }
  if (value && typeof value === "object" && "id" in value) {
    const normalized = String((value as { id?: unknown }).id || "").trim();
    return normalized || null;
  }
  return null;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const webhookSecret = Deno.env.get("STRIPE_WEBHOOK_SECRET") || "";
  const supabaseUrl = Deno.env.get("SUPABASE_URL") || "";
  const serviceRole = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
  if (!webhookSecret || !supabaseUrl || !serviceRole) {
    return new Response("Webhook is not configured", { status: 503 });
  }

  const rawBody = await req.text();
  const signature = req.headers.get("Stripe-Signature") || "";
  if (!(await verifyStripeSignature(rawBody, signature, webhookSecret))) {
    return new Response("Invalid Stripe signature", { status: 400 });
  }

  let event: any;
  try {
    event = JSON.parse(rawBody);
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  const supabase = createClient(supabaseUrl, serviceRole, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const type = String(event?.type || "");
  const obj = event?.data?.object || {};
  let applied: boolean | null = null;

  try {
    if (type === "checkout.session.completed") {
      const userId = String(
        obj.client_reference_id || obj.metadata?.user_id || "",
      ).trim();

      if (userId) {
        const plan = normalizePlan(obj.metadata?.plan);
        if (!PAID_PLANS.has(plan)) {
          return new Response("Missing or invalid checkout plan metadata", {
            status: 400,
          });
        }

        const { data: existing, error: existingError } = await supabase
          .from("subscriptions")
          .select("status")
          .eq("user_id", userId)
          .maybeSingle();
        if (existingError) throw existingError;

        // Checkout completion links Stripe identifiers, but the Subscription
        // object remains the authority for entitlement status. Preserve an
        // already-applied subscription status if Stripe delivered that event
        // before checkout.session.completed.
        const currentStatus = normalizeStatus(existing?.status);
        const checkoutStatus =
          currentStatus === "none" ? "incomplete" : currentStatus;

        const { error } = await supabase.from("subscriptions").upsert(
          {
            user_id: userId,
            plan,
            status: checkoutStatus,
            stripe_customer_id: stripeId(obj.customer),
            stripe_subscription_id: stripeId(obj.subscription),
          },
          { onConflict: "user_id" },
        );
        if (error) throw error;
        applied = true;
      }
    }

    if (
      type === "customer.subscription.created" ||
      type === "customer.subscription.updated" ||
      type === "customer.subscription.deleted"
    ) {
      const eventId = String(event?.id || "").trim();
      const eventCreatedAt = isoFromUnix(event?.created);
      if (!eventId || !eventCreatedAt) {
        return new Response("Stripe event id/created timestamp is required", {
          status: 400,
        });
      }

      let userId = String(obj.metadata?.user_id || "").trim();
      let existingPlan: string | null = null;

      if (!userId && obj.id) {
        const { data, error } = await supabase
          .from("subscriptions")
          .select("user_id, plan")
          .eq("stripe_subscription_id", String(obj.id))
          .maybeSingle();
        if (error) throw error;
        userId = String(data?.user_id || "").trim();
        existingPlan = data?.plan ? normalizePlan(data.plan) : null;
      }

      if (userId) {
        const priceId = obj.items?.data?.[0]?.price?.id || null;
        let plan =
          planFromPriceId(priceId) || normalizePlan(obj.metadata?.plan);

        if (!PAID_PLANS.has(plan)) {
          if (!existingPlan) {
            const { data, error } = await supabase
              .from("subscriptions")
              .select("plan")
              .eq("user_id", userId)
              .maybeSingle();
            if (error) throw error;
            existingPlan = data?.plan ? normalizePlan(data.plan) : null;
          }
          plan = existingPlan || "demo";
        }

        if (!PAID_PLANS.has(plan)) {
          return new Response(
            "Missing or invalid subscription plan/price mapping",
            { status: 400 },
          );
        }

        const status =
          type === "customer.subscription.deleted"
            ? "canceled"
            : normalizeStatus(obj.status);

        const { data, error } = await supabase.rpc(
          "apply_market_forecaster_subscription_event",
          {
            p_user_id: userId,
            p_plan: plan,
            p_status: status,
            p_stripe_customer_id: stripeId(obj.customer),
            p_stripe_subscription_id: stripeId(obj.id),
            p_stripe_price_id: priceId,
            p_current_period_end: isoFromUnix(obj.current_period_end),
            p_cancel_at_period_end: Boolean(obj.cancel_at_period_end),
            p_stripe_event_id: eventId,
            p_stripe_event_type: type,
            p_stripe_event_created_at: eventCreatedAt,
          },
        );
        if (error) throw error;
        applied = data === true;
      }
    }
  } catch (err) {
    console.error("Stripe webhook persistence error", err);
    return new Response("Persistence failed", { status: 500 });
  }

  return new Response(
    JSON.stringify({
      received: true,
      applied,
      ignored_stale_event: applied === false,
    }),
    {
      status: 200,
      headers: { "Content-Type": "application/json" },
    },
  );
});
