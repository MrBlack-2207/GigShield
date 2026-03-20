# gigshield/backend/app/services/policy_service.py

from datetime import date, datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.policy  import Policy
from app.models.worker  import Worker
from app.models.claim   import Claim
from app.engine.premium_calculator import calculate_premium, get_current_season
from app.services.audit_service    import write_audit


def create_policy(
    db:        Session,
    worker_id: str,
    zone_id:   str,
) -> Policy:
    """
    Creates a new weekly policy for a worker.
    - Reads income_tier from the worker's registered profile
    - Computes premium using the locked formula
    - Sets 48-hour lookback exclusion window
    - Enforces: only one ACTIVE policy per worker at a time
    """
    # ── Enforce one active policy per worker ────────────────────────────
    existing = (
        db.query(Policy)
        .filter(Policy.worker_id == worker_id, Policy.status == "ACTIVE")
        .first()
    )
    if existing:
        raise ValueError("Worker already has an active policy this week.")

    worker: Worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise ValueError(f"Worker {worker_id} not found.")

    # ── Compute premium ──────────────────────────────────────────────────
    season    = get_current_season()
    breakdown = calculate_premium(worker.income_tier, season)

    # ── Week boundaries (today → +7 days) ───────────────────────────────
    today      = date.today()
    week_start = today
    week_end   = today + timedelta(days=7)

    # ── 48-hour lookback exclusion ───────────────────────────────────────
    lookback_until = datetime.now(timezone.utc) + timedelta(hours=48)

    policy = Policy(
        worker_id=worker_id,
        zone_id=zone_id,
        income_tier=worker.income_tier,
        weekly_premium_inr=breakdown.weekly_premium_inr,
        coverage_ratio=breakdown.coverage_ratio,
        weekly_payout_cap=breakdown.weekly_payout_cap_inr,
        season_at_purchase=season,
        week_start=week_start,
        week_end=week_end,
        status="ACTIVE",
        lookback_exclusion_until=lookback_until,
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
            "worker_id":         worker_id,
            "income_tier":       worker.income_tier,
            "weekly_premium":    breakdown.weekly_premium_inr,
            "weekly_payout_cap": breakdown.weekly_payout_cap_inr,
            "season":            season,
        },
    )
    return policy


def get_active_policy(db: Session, worker_id: str) -> Policy | None:
    return (
        db.query(Policy)
        .filter(Policy.worker_id == worker_id, Policy.status == "ACTIVE")
        .first()
    )


def get_policy_by_id(db: Session, policy_id: str) -> Policy | None:
    return db.query(Policy).filter(Policy.policy_id == policy_id).first()


def get_worker_claims(db: Session, worker_id: str) -> list[Claim]:
    return (
        db.query(Claim)
        .filter(Claim.worker_id == worker_id)
        .order_by(Claim.triggered_at.desc())
        .all()
    )