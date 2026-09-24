import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";
import { createRemoteJWKSet, jwtVerify } from "npm:jose@6";

const EXPECTED_REPOSITORY = "saldana201/market_forecaster_v2";
const EXPECTED_REF = "refs/heads/master";
const EXPECTED_WORKFLOW =
  "saldana201/market_forecaster_v2/.github/workflows/refresh_demo_contracts.yml@";
const EXPECTED_AUDIENCE = "market-forecaster-supabase";
const GITHUB_ISSUER = "https://token.actions.githubusercontent.com";
const GITHUB_JWKS = createRemoteJWKSet(
  new URL("https://token.actions.githubusercontent.com/.well-known/jwks"),
);

const DEMO_TICKERS = [
  "AAPL", "MSFT", "JPM", "BAC", "LLY", "JNJ", "XOM",
  "CVX", "WMT", "COST", "CAT", "GE", "SPY", "QQQ",
];
const DEMO_SET = new Set(DEMO_TICKERS);
const EXPECTED_HORIZONS = [1, 5, 10, 20];

type Claims = {
  repository?: string;
  ref?: string;
  workflow_ref?: string;
  job_workflow_ref?: string;
  event_name?: string;
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function verifyGitHubOidc(req: Request): Promise<Claims> {
  const auth = req.headers.get("Authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!token) throw new Error("missing GitHub OIDC bearer token");

  const { payload } = await jwtVerify(token, GITHUB_JWKS, {
    issuer: GITHUB_ISSUER,
    audience: EXPECTED_AUDIENCE,
  });

  const claims = payload as Claims;
  const workflowRef = String(
    claims.workflow_ref || claims.job_workflow_ref || "",
  );
  const eventName = String(claims.event_name || "");

  if (claims.repository !== EXPECTED_REPOSITORY) {
    throw new Error("unexpected GitHub repository");
  }
  if (claims.ref !== EXPECTED_REF) {
    throw new Error("publisher must run from master");
  }
  if (!workflowRef.startsWith(EXPECTED_WORKFLOW)) {
    throw new Error("unexpected GitHub workflow");
  }
  if (!["schedule", "workflow_dispatch"].includes(eventName)) {
    throw new Error("unexpected GitHub event");
  }

  return claims;
}

function validateContract(contract: any): string | null {
  const ticker = String(contract?.ticker || "").toUpperCase();
  if (!DEMO_SET.has(ticker)) return "ticker is not in the Demo universe";
  if (!contract?.contract_id) return "contract_id is required";
  if (!contract?.generated_at) return "generated_at is required";
  if (contract?.schema_version !== "4.0-forecast-contract-v1") {
    return "unexpected Forecast Contract schema";
  }
  if (contract?.scope !== "FORECAST_ONLY") return "scope must be FORECAST_ONLY";
  if (contract?.status !== "READY") return "contract must be READY";

  const horizons = (Array.isArray(contract?.forecasts)
    ? contract.forecasts
    : [])
    .map((row: any) => Number(row?.horizon_days))
    .sort((a: number, b: number) => a - b);

  if (
    horizons.length !== EXPECTED_HORIZONS.length ||
    horizons.some((value: number, index: number) =>
      value !== EXPECTED_HORIZONS[index]
    )
  ) {
    return "contract must contain 1D/5D/10D/20D horizons";
  }
  return null;
}

Deno.serve(async (req: Request) => {
  try {
    await verifyGitHubOidc(req);
  } catch (err) {
    console.error("GitHub OIDC verification failed", err);
    return jsonResponse({ error: "unauthorized publisher" }, 401);
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL") || "";
  const serviceRole = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
  if (!supabaseUrl || !serviceRole) {
    return jsonResponse({ error: "publisher backend is not configured" }, 503);
  }

  const supabase = createClient(supabaseUrl, serviceRole, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  if (req.method === "GET") {
    const { data, error } = await supabase
      .from("shared_forecast_authority")
      .select("config,revision,updated_at")
      .eq("authority_key", "active")
      .single();

    if (error || !data?.config) {
      console.error("Shared authority fetch failed", error);
      return jsonResponse({ error: "shared authority unavailable" }, 503);
    }

    return jsonResponse({
      config: data.config,
      revision: data.revision,
      updated_at: data.updated_at,
    });
  }

  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  let payload: any;
  try {
    payload = await req.json();
  } catch {
    return jsonResponse({ error: "invalid JSON" }, 400);
  }

  const contracts = Array.isArray(payload?.contracts)
    ? payload.contracts
    : [];
  if (contracts.length !== DEMO_TICKERS.length) {
    return jsonResponse({
      error: "expected exactly 14 Demo Forecast Contracts",
      received: contracts.length,
    }, 422);
  }

  const seen = new Set<string>();
  for (const contract of contracts) {
    const ticker = String(contract?.ticker || "").toUpperCase();
    if (seen.has(ticker)) {
      return jsonResponse({ error: `duplicate contract for ${ticker}` }, 422);
    }
    seen.add(ticker);

    const validationError = validateContract(contract);
    if (validationError) {
      return jsonResponse({
        error: `${ticker || "UNKNOWN"}: ${validationError}`,
      }, 422);
    }
  }

  if (
    seen.size !== DEMO_SET.size ||
    DEMO_TICKERS.some((ticker) => !seen.has(ticker))
  ) {
    return jsonResponse({
      error: "payload does not match the complete Demo universe",
    }, 422);
  }

  const rows = contracts.map((contract: any) => ({
    ticker: String(contract.ticker).toUpperCase(),
    contract_id: String(contract.contract_id),
    generated_at: contract.generated_at,
    as_of: contract.as_of ?? null,
    status: String(contract.status),
    schema_version: contract.schema_version,
    contract,
  }));

  const { error: upsertError } = await supabase
    .from("shared_forecast_contracts")
    .upsert(rows, { onConflict: "ticker" });

  if (upsertError) {
    console.error("Shared Forecast Contract publish failed", upsertError);
    return jsonResponse({ error: "shared publish failed" }, 500);
  }

  const { data: verified, error: verifyError } = await supabase
    .from("shared_forecast_contracts")
    .select("ticker,contract_id,generated_at,status")
    .in("ticker", DEMO_TICKERS);

  if (verifyError || !verified || verified.length !== DEMO_TICKERS.length) {
    console.error("Shared Forecast Contract verification failed", verifyError);
    return jsonResponse({ error: "shared publish verification failed" }, 500);
  }

  const expectedIds = new Map(
    rows.map((row: any) => [row.ticker, row.contract_id]),
  );
  for (const row of verified) {
    if (
      row.status !== "READY" ||
      expectedIds.get(row.ticker) !== row.contract_id
    ) {
      return jsonResponse({
        error: "shared publish verification mismatch",
        ticker: row.ticker,
      }, 500);
    }
  }

  return jsonResponse({
    published: verified.length,
    tickers: verified.map((row: any) => row.ticker).sort(),
    generated_at: verified.map((row: any) => ({
      ticker: row.ticker,
      generated_at: row.generated_at,
    })),
  });
});
