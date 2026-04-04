# gigshield/backend/app/schemas/policy.py

from pydantic import BaseModel
from datetime import date, datetime
from typing import Literal, Optional


class PolicyCreateRequest(BaseModel):
    worker_id: str
    zone_id:   str
    tenure_months: Literal[1, 3, 6, 12]


class PolicyOut(BaseModel):
    policy_id:          str
    worker_id:          str
    zone_id:            str
    income_tier:        int
    weekly_premium_inr: float
    coverage_ratio:     float
    weekly_payout_cap:  float
    season_at_purchase: str
    tenure_months:      int
    start_date:         datetime
    end_date:           datetime
    billing_cycle:      str
    last_premium_paid_at: datetime
    next_premium_due_at: datetime
    cooldown_ends_at:   datetime
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
