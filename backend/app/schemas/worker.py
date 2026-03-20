# gigshield/backend/app/schemas/worker.py

from pydantic import BaseModel, field_validator
from typing import Optional


class WorkerRegisterRequest(BaseModel):
    full_name:   str
    phone:       str
    income_tier: int
    zone_id:     str
    platform:    str
    aadhaar:     Optional[str] = None

    @field_validator("income_tier")
    @classmethod
    def tier_must_be_valid(cls, v):
        if v not in [400, 600, 800]:
            raise ValueError("income_tier must be 400, 600, or 800")
        return v

    @field_validator("platform")
    @classmethod
    def platform_must_be_valid(cls, v):
        if v not in ["ZEPTO", "BLINKIT", "BOTH"]:
            raise ValueError("platform must be ZEPTO, BLINKIT, or BOTH")
        return v


class WorkerOut(BaseModel):
    worker_id:       str
    full_name:       str
    phone:           str
    income_tier:     int
    primary_zone_id: str
    platform:        str
    kyc_status:      str
    is_active:       bool

    class Config:
        from_attributes = True