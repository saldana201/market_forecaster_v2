"""Drift monitoring and deployment-policy API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from market_forecaster.core.deployment_policy import (
    approve_champion,
    deployment_policy_state,
    load_governance_events,
)

router = APIRouter()


class ChampionApprovalRequest(BaseModel):
    candidate: str
    approved_by: str = Field(min_length=2, max_length=128)
    rationale: str = Field(min_length=10, max_length=2000)


@router.get("/deployment-policy/{ticker}")
async def get_deployment_policy(ticker: str):
    symbol = ticker.upper().strip()
    state = deployment_policy_state(symbol)
    state["approval_events"] = load_governance_events(symbol)[-50:]
    return state


@router.post("/deployment-policy/{ticker}/approve")
async def approve_deployment_champion(ticker: str, request: ChampionApprovalRequest):
    symbol = ticker.upper().strip()
    try:
        event = approve_champion(
            symbol,
            request.candidate,
            request.approved_by,
            request.rationale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        "ticker": symbol,
        "approval": event,
        "deployment_policy": deployment_policy_state(symbol),
    }
