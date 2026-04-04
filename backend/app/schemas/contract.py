from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class StoreOut(BaseModel):
    id: str
    name: str
    platform: str
    zone_id: str
    zone_name: Optional[str] = None
    location: Optional[dict] = None


class WorkerRegisterOut(BaseModel):
    worker_id: str
    full_name: str
    phone: str
    income_tier: int
    primary_zone_id: str
    platform: str
    external_worker_id: Optional[str] = None
    home_store_id: str
    kyc_status: str
    is_active: bool


class PolicyQuoteRequest(BaseModel):
    worker_id: str
    tenure_months: Literal[1, 3, 6, 12] = 1
    zone_id: Optional[str] = None
    season: Optional[str] = None


class PolicyQuoteOut(BaseModel):
    worker_id: str
    zone_id: str
    tenure_months: int
    billing_cycle: str
    first_weekly_premium_at_purchase: bool
    cooldown_hours: int
    season: str
    weekly_premium_inr: float
    weekly_payout_cap_inr: float
    coverage_ratio: float
    expected_weekly_loss: float
    seasonal_disruption_days: float
    disruption_days_source: str


class PolicyPurchaseRequest(BaseModel):
    worker_id: str
    tenure_months: Literal[1, 3, 6, 12]
    zone_id: Optional[str] = None


class WorkerPolicyOut(BaseModel):
    policy_id: str
    worker_id: str
    zone_id: str
    tenure_months: int
    status: str
    effective_status: str
    billing_cycle: str
    weekly_premium_inr: float
    weekly_payout_cap_inr: float
    start_date: datetime
    end_date: datetime
    cooldown_ends_at: datetime
    next_premium_due_at: datetime
    payout_eligible_now: bool


class WorkerPolicyEnvelope(BaseModel):
    worker_id: str
    policy: Optional[WorkerPolicyOut] = None


class ZDITransparencyOut(BaseModel):
    base_zdi: Optional[float] = None
    event_boost_total: Optional[float] = None
    final_zdi: Optional[float] = None
    timestamp: Optional[datetime] = None


class ClaimTimelineItemOut(BaseModel):
    claim_id: str
    policy_id: str
    disruption_event_id: str
    zone_id: str
    status: str
    triggered_at: datetime
    paid_at: Optional[datetime] = None
    base_zdi: Optional[float] = None
    event_boost_total: Optional[float] = None
    final_zdi: Optional[float] = None
    affected_hours_used: float
    affected_hours_source: str
    payout_rate_used: float
    payout_rate_source: str
    payout_amount: float
    wallet_credited: bool


class ClaimsTimelineOut(BaseModel):
    worker_id: str
    items: list[ClaimTimelineItemOut]


class WalletLedgerEntryMiniOut(BaseModel):
    id: str
    amount_inr: float
    entry_type: str
    reference_id: Optional[str] = None
    created_at: datetime


class WorkerWalletOut(BaseModel):
    worker_id: str
    wallet_id: Optional[str] = None
    wallet_balance_inr: float
    updated_at: Optional[datetime] = None
    recent_entries: list[WalletLedgerEntryMiniOut] = Field(default_factory=list)


class WorkerCashoutOut(BaseModel):
    withdrawal_id: str
    withdrawn_amount: float
    remaining_wallet_balance: float
    status: str


class WorkerDashboardOut(BaseModel):
    worker_id: str
    full_name: str
    platform: str
    home_store_id: str
    primary_zone_id: str
    policy: Optional[WorkerPolicyOut] = None
    wallet_balance_inr: float
    claims_count: int
    paid_claims_count: int
    total_payout_paid_inr: float
    latest_zdi: Optional[ZDITransparencyOut] = None
    recent_claims: list[ClaimTimelineItemOut] = Field(default_factory=list)


class DemoActivatePolicyOut(BaseModel):
    worker_id: str
    policy_id: str
    previous_status: str
    new_status: str
    cooldown_ends_at: datetime
    next_premium_due_at: datetime


class DemoTriggerFireRequest(BaseModel):
    cycles: int = Field(default=1, ge=1, le=5)
    worker_id: Optional[str] = None
    zone_id: Optional[str] = None
    scenario: Literal["none", "outage_on", "outage_off", "outage_pulse"] = "none"


class DemoTriggerFireOut(BaseModel):
    status: str
    cycles: int
    scenario: str
    target_zone_id: Optional[str] = None
    last_zdi: Optional[ZDITransparencyOut] = None


class DemoClaimsRunRequest(BaseModel):
    worker_id: Optional[str] = None
    limit: int = Field(default=200, ge=1, le=1000)
    skip_fraud_checks: bool = True


class DemoClaimsRunOut(BaseModel):
    status: str
    processed: int
    approved: int
    flagged: int
    paid: int
