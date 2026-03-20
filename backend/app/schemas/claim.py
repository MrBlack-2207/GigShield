# gigshield/backend/app/schemas/claim.py

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ClaimOut(BaseModel):
    claim_id:         str
    policy_id:        str
    worker_id:        str
    zone_id:          str
    disruption_level: str
    payout_pct:       int
    affected_hours:   float
    gross_payout_inr: float
    final_payout_inr: float
    cap_applied:      bool
    fraud_flag:       bool
    status:           str
    triggered_at:     datetime
    paid_at:          Optional[datetime]

    class Config:
        from_attributes = True