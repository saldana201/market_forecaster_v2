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

function isoFromUnix(value: unknown): string | null {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return null;
  return new Date(seconds * 1000).toISOString();
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

  try {
    if (type === "checkout.session.completed") {
      const userId = String(
        obj.client_reference_id || obj.metadata?.user_id || "",
      ).trim();
      if (userId) {
        const plan = normalizePlan(obj.metadata?.plan);
        const { error } = await supabase.from("subscriptions").upsert(
          {
            user_id: userId,
            plan,
            status: "incomplete",
            stripe_customer_id:
              typeof obj.customer === "string" ? obj.customer : obj.customer?.id || null,
            stripe_subscription_id:
              typeof obj.subscription === "string"
                ? obj.subscription
                : obj.subscription?.id || null,
          },
          { onConflict: "user_id" },
        );
        if (error) throw error;
      }
    }

    if (
      type === "customer.subscription.created" ||
      type === "customer.subscription.updated" ||
      type === "customer.subscription.deleted"
    ) {
      let userId = String(obj.metadata?.user_id || "").trim();

      if (!userId && obj.id) {
        const { data, error } = await supabase
          .from("subscriptions")
          .select("user_id")
          .eq("stripe_subscription_id", String(obj.id))
          .maybeSingle();
        if (error) throw error;
        userId = String(data?.user_id || "").trim();
      }

      if (userId) {
        const status =
          type === "customer.subscription.deleted"
            ? "canceled"
            : normalizeStatus(obj.status);
        const priceId = obj.items?.data?.[0]?.price?.id || null;
        const plan = normalizePlan(obj.metadata?.plan);

        const { error } = await supabase.from("subscriptions").upsert(
          {
            user_id: userId,
            plan,
            status,
            stripe_customer_id:
              typeof obj.customer === "string" ? obj.customer : obj.customer?.id || null,
            stripe_subscription_id: obj.id || null,
            stripe_price_id: priceId,
            current_period_end: isoFromUnix(obj.current_period_end),
            cancel_at_period_end: Boolean(obj.cancel_at_period_end),
          },
          { onConflict: "user_id" },
        );
        if (error) throw error;
      }
    }
  } catch (err) {
    console.error("Stripe webhook persistence error", err);
    return new Response("Persistence failed", { status: 500 });
  }

  return new Response(JSON.stringify({ received: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
});
