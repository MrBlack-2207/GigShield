# gigshield/backend/app/schemas/worker.py

from pydantic import BaseModel, field_validator, model_validator
from typing import Optional

from app.constants.platforms import PLATFORMS, normalize_platform


class WorkerRegisterRequest(BaseModel):
    full_name:   str
    phone:       str
    income_tier: int
    zone_id:     Optional[str] = None
    home_store_id: Optional[str] = None
    platform:    str
    external_worker_id: Optional[str] = None
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
        normalized = normalize_platform(v)
        if not normalized:
            allowed = ", ".join(PLATFORMS)
            raise ValueError(f"platform must be one of: {allowed}")
        return normalized

    @model_validator(mode="after")
    def zone_or_store_required(self):
        if not self.zone_id and not self.home_store_id:
            raise ValueError("Either zone_id or home_store_id is required")
        return self


class WorkerOut(BaseModel):
    worker_id:       str
    full_name:       str
    phone:           str
    income_tier:     int
    primary_zone_id: str
    platform:        str
    external_worker_id: Optional[str]
    home_store_id:   str
    kyc_status:      str
    is_active:       bool

    class Config:
        from_attributes = True
