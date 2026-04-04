import calendar
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.engine.premium_calculator import calculate_premium, get_current_season
from app.models.claim import Claim
from app.models.policy import Policy
from app.models.worker import Worker
from app.services.audit_service import write_audit
from app.services.disruption_frequency_inference import predict_disruption_frequency_days

ALLOWED_TENURE_MONTHS = {1, 3, 6, 12}
ACTIVE_OR_PENDING_STATUSES = {"active", "pending_activation"}


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _add_months_utc(dt: datetime, months: int) -> datetime:
    src = _to_utc(dt)
    year = src.year + ((src.month - 1 + months) // 12)
    month = ((src.month - 1 + months) % 12) + 1
    day = min(src.day, calendar.monthrange(year, month)[1])
    return src.replace(year=year, month=month, day=day)


def _normalize_status(status: str | None) -> str:
    value = (status or "").strip().lower()
    if value == "suspended":
        return "inactive"
    if value == "active":
        return "active"
    if value == "pending_activation":
        return "pending_activation"
    if value == "inactive":
        return "inactive"
    if value == "expired":
        return "expired"
    if value == "cancelled":
        return "cancelled"
    return "inactive"


def derive_effective_policy_status(policy: Policy, at_time: datetime | None = None) -> str:
    """
    Derives effective lifecycle status from policy lifecycle fields.
    This function does not write to DB.
    """
    now = _to_utc(at_time or datetime.now(timezone.utc))
    stored_status = _normalize_status(policy.status)

    if stored_status == "cancelled":
        return "cancelled"

    start_date = _to_utc(policy.start_date or policy.created_at or now)
    end_date = _to_utc(policy.end_date or _add_months_utc(start_date, int(policy.tenure_months or 1)))
    next_due = _to_utc(policy.next_premium_due_at or (start_date + timedelta(days=7)))
    cooldown_ends = _to_utc(policy.cooldown_ends_at or (start_date + timedelta(hours=48)))

    if now >= end_date:
        return "expired"
    if now > next_due:
        return "inactive"
    if stored_status == "inactive":
        return "inactive"
    if now < cooldown_ends:
        return "pending_activation"
    return "active"


def sync_policy_status_in_flow(
    db: Session,
    policy: Policy,
    at_time: datetime | None = None,
) -> str:
    """
    Controlled-flow persistence of status transitions.
    Safe to call in purchase / payout eligibility / renewal flows.
    """
    effective = derive_effective_policy_status(policy, at_time)
    if policy.status != effective:
        policy.status = effective
        db.add(policy)
    return effective


def is_policy_payout_eligible(policy: Policy, at_time: datetime | None = None) -> bool:
    """
    Eligibility source of truth:
    - policy status must be effectively active
    - now between start_date and end_date
    - now <= next_premium_due_at (billing current)
    - now >= cooldown_ends_at
    """
    now = _to_utc(at_time or datetime.now(timezone.utc))
    start_date = _to_utc(policy.start_date or policy.created_at or now)
    end_date = _to_utc(policy.end_date or _add_months_utc(start_date, int(policy.tenure_months or 1)))
    next_due = _to_utc(policy.next_premium_due_at or (start_date + timedelta(days=7)))
    cooldown_ends = _to_utc(policy.cooldown_ends_at or (start_date + timedelta(hours=48)))
    effective = derive_effective_policy_status(policy, now)

    return (
        effective == "active"
        and start_date <= now < end_date
        and now <= next_due
        and now >= cooldown_ends
    )


def create_policy(
    db: Session,
    worker_id: str,
    zone_id: str,
    tenure_months: int,
) -> Policy:
    """
    Creates a tenure-based policy with weekly billing metadata.

    Billing logic:
    - First weekly premium is considered paid at purchase.
    - Coverage remains current until next_premium_due_at.
    - If no renewal payment is recorded by next_premium_due_at, policy becomes inactive.
    """
    if tenure_months not in ALLOWED_TENURE_MONTHS:
        raise ValueError("tenure_months must be one of: 1, 3, 6, 12.")

    now = datetime.now(timezone.utc)

    # Controlled flow: normalize existing lifecycle statuses before overlap check.
    existing_policies = db.query(Policy).filter(Policy.worker_id == worker_id).all()
    for policy in existing_policies:
        effective = sync_policy_status_in_flow(db, policy, now)
        if effective in ACTIVE_OR_PENDING_STATUSES:
            raise ValueError("Worker already has an active or pending-activation policy.")

    worker: Worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise ValueError(f"Worker {worker_id} not found.")

    season = get_current_season()
    freq_result = predict_disruption_frequency_days(db=db, zone_id=zone_id, at_time=now)
    breakdown = calculate_premium(
        worker.income_tier,
        season,
        seasonal_disruption_days_override=freq_result.seasonal_disruption_days,
        disruption_days_source=freq_result.source,
    )

    start_date = now
    end_date = _add_months_utc(start_date, tenure_months)
    cooldown_ends = start_date + timedelta(hours=48)
    next_premium_due = start_date + timedelta(days=7)

    policy = Policy(
        worker_id=worker_id,
        zone_id=zone_id,
        income_tier=worker.income_tier,
        weekly_premium_inr=breakdown.weekly_premium_inr,
        coverage_ratio=breakdown.coverage_ratio,
        weekly_payout_cap=breakdown.weekly_payout_cap_inr,
        season_at_purchase=season,
        tenure_months=tenure_months,
        start_date=start_date,
        end_date=end_date,
        billing_cycle="weekly",
        last_premium_paid_at=start_date,
        next_premium_due_at=next_premium_due,
        cooldown_ends_at=cooldown_ends,
        week_start=start_date.date(),
        week_end=(start_date + timedelta(days=7)).date(),
        status="pending_activation",
        lookback_exclusion_until=cooldown_ends,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)

    write_audit(
        db=db,
        event_type="POLICY_CREATED",
        entity_type="Policy",
        entity_id=policy.policy_id,
        zone_id=zone_id,
        payload={
            "worker_id": worker_id,
            "income_tier": worker.income_tier,
            "weekly_premium": breakdown.weekly_premium_inr,
            "weekly_payout_cap": breakdown.weekly_payout_cap_inr,
            "season": season,
            "disruption_days_used": breakdown.seasonal_disruption_days,
            "disruption_days_source": breakdown.disruption_days_source,
            "disruption_days_reason": freq_result.reason,
            "disruption_days_model_path": freq_result.model_path,
            "tenure_months": tenure_months,
            "billing_cycle": "weekly",
            "first_weekly_premium_paid_at": start_date.isoformat(),
            "next_premium_due_at": next_premium_due.isoformat(),
            "cooldown_ends_at": cooldown_ends.isoformat(),
        },
    )
    return policy


def get_active_policy(db: Session, worker_id: str) -> Policy | None:
    now = datetime.now(timezone.utc)
    policies = (
        db.query(Policy)
        .filter(Policy.worker_id == worker_id)
        .order_by(Policy.created_at.desc())
        .all()
    )
    for policy in policies:
        if derive_effective_policy_status(policy, now) in ACTIVE_OR_PENDING_STATUSES:
            return policy
    return None


def get_policy_by_id(db: Session, policy_id: str) -> Policy | None:
    return db.query(Policy).filter(Policy.policy_id == policy_id).first()


def get_worker_claims(db: Session, worker_id: str) -> list[Claim]:
    return (
        db.query(Claim)
        .filter(Claim.worker_id == worker_id)
        .order_by(Claim.triggered_at.desc())
        .all()
    )
