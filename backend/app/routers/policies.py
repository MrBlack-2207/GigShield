# gigshield/backend/app/routers/policies.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.policy import (
    PolicyCreateRequest, PolicyOut,
    PremiumPreviewRequest, PremiumPreviewOut,
)
from app.services import create_policy, get_active_policy, get_policy_by_id
from app.engine.premium_calculator import calculate_premium, get_current_season

router = APIRouter()


@router.post("/preview", response_model=PremiumPreviewOut)
def preview_premium(body: PremiumPreviewRequest):
    """
    Returns premium breakdown before purchase.
    Called by the mobile app on the policy screen
    so the worker sees the cost before confirming.
    """
    season = body.season or get_current_season()
    try:
        b = calculate_premium(body.income_tier, season)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PremiumPreviewOut(
        income_tier=b.income_tier,
        season=b.season,
        weekly_premium_inr=b.weekly_premium_inr,
        weekly_payout_cap_inr=b.weekly_payout_cap_inr,
        coverage_ratio=b.coverage_ratio,
        expected_weekly_loss=b.expected_weekly_loss,
    )


@router.post("/", response_model=PolicyOut, status_code=201)
def purchase_policy(body: PolicyCreateRequest, db: Session = Depends(get_db)):
    try:
        policy = create_policy(db, body.worker_id, body.zone_id)
        return policy
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/active/{worker_id}", response_model=PolicyOut)
def get_active(worker_id: str, db: Session = Depends(get_db)):
    policy = get_active_policy(db, worker_id)
    if not policy:
        raise HTTPException(status_code=404, detail="No active policy for this worker")
    return policy


@router.get("/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: str, db: Session = Depends(get_db)):
    policy = get_policy_by_id(db, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy
