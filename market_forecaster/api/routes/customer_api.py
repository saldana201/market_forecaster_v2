"""Customer-facing Pro API account and quota routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class CustomerAPIUsageSchema(BaseModel):
    key_prefix: str
    plan: str
    subscription_status: str
    monthly_limit: int
    used: int
    remaining: int
    period_start: str
    period_end: str


@router.get("/api/usage", response_model=CustomerAPIUsageSchema)
async def customer_api_usage(request: Request) -> CustomerAPIUsageSchema:
    """Return the caller's current account-wide Pro API allowance.

    The request itself is an authenticated billable API request and is included
    in the returned usage count.
    """
    principal = getattr(request.state, "api_principal", None)
    usage = getattr(request.state, "api_usage", None)
    if not isinstance(principal, dict) or principal.get("type") != "customer":
        raise HTTPException(status_code=403, detail="Pro customer API key required")
    if usage is None:
        raise HTTPException(
            status_code=503,
            detail="Customer API usage metering is unavailable",
        )

    return CustomerAPIUsageSchema(
        key_prefix=str(principal.get("key_prefix") or ""),
        plan=str(principal.get("plan") or "pro"),
        subscription_status=str(
            principal.get("subscription_status") or "unknown"
        ),
        monthly_limit=int(usage.monthly_limit),
        used=int(usage.used),
        remaining=int(usage.remaining),
        period_start=str(usage.period_start),
        period_end=str(usage.period_end),
    )
