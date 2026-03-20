# gigshield/backend/app/schemas/policy.py

from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class PolicyCreateRequest(BaseModel):
    worker_id: str
    zone_id:   str


class PolicyOut(BaseModel):
    policy_id:          str
    worker_id:          str
    zone_id:            str
    income_tier:        int
    weekly_premium_inr: float
    coverage_ratio:     float
    weekly_payout_cap:  float
    season_at_purchase: str
    week_start:         date
    week_end:           date
    status:             str

    class Config:
        from_attributes = True


class PremiumPreviewRequest(BaseModel):
    income_tier: int
    season:      Optional[str] = None


class PremiumPreviewOut(BaseModel):
    income_tier:          int
    season:               str
    weekly_premium_inr:   float
    weekly_payout_cap_inr: float
    coverage_ratio:       float
    expected_weekly_loss: float