# gigshield/backend/app/engine/claims_engine.py

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.policy          import Policy
from app.models.claim           import Claim
from app.models.disruption_event import DisruptionEvent
from app.config import get_settings

settings = get_settings()

WORKING_HOURS = settings.WORKING_HOURS_PER_DAY
COVERAGE_RATIO = settings.COVERAGE_RATIO


def compute_payout(
    income_tier:           int,
    payout_pct:            int,
    affected_hours:        float,
    weekly_payout_cap:     float,
    week_total_paid_so_far: float,
) -> tuple[float, float, bool]:
    """
    Prorated payout formula (locked from design doc):
        gross = payout_pct% × (affected_hours / WORKING_HOURS) × income_tier × coverage_ratio

    Returns (gross_payout, final_payout, cap_applied).
    final_payout is capped at (weekly_payout_cap - already_paid_this_week).
    """
    gross = (
        (payout_pct / 100)
        * (affected_hours / WORKING_HOURS)
        * income_tier
        * COVERAGE_RATIO
    )
    gross = round(gross, 2)

    remaining_cap = max(0.0, float(weekly_payout_cap) - week_total_paid_so_far)
    final         = round(min(gross, remaining_cap), 2)
    cap_applied   = final < gross

    return gross, final, cap_applied


def trigger_claims_for_event(
    db: Session,
    event: DisruptionEvent,
) -> list[Claim]:
    """
    Called immediately after a DisruptionEvent is closed.

    1. Finds all ACTIVE policies in the affected zone.
    2. Applies lookback exclusion (48hr window after policy creation).
    3. Computes prorated payout for each worker.
    4. Creates Claim rows with status=PENDING.
    5. Returns the list of created claims for the fraud checker.
    """
    now = datetime.now(timezone.utc)

    active_policies: list[Policy] = (
        db.query(Policy)
        .filter(
            Policy.zone_id == event.zone_id,
            Policy.status  == "ACTIVE",
        )
        .all()
    )

    created_claims: list[Claim] = []

    for policy in active_policies:

        # ── Lookback exclusion check ──────────────────────────────────────
        if policy.lookback_exclusion_until:
            exclusion_dt = policy.lookback_exclusion_until
            if exclusion_dt.tzinfo is None:
                exclusion_dt = exclusion_dt.replace(tzinfo=timezone.utc)
            if now < exclusion_dt:
                # Policy too new — skip silently
                continue

        # ── Compute how much has already been paid this week ──────────────
        week_paid = _get_week_total_paid(db, policy.policy_id, event.started_at)

        # ── Compute payout ────────────────────────────────────────────────
        gross, final, cap_applied = compute_payout(
            income_tier=policy.income_tier,
            payout_pct=event.peak_level and _level_to_pct(event.peak_level) or 0,
            affected_hours=float(event.affected_hours or 0),
            weekly_payout_cap=float(policy.weekly_payout_cap),
            week_total_paid_so_far=week_paid,
        )

        if final <= 0:
            continue  # Nothing to pay — cap exhausted or zero disruption

        claim = Claim(
            policy_id=policy.policy_id,
            worker_id=policy.worker_id,
            disruption_event_id=event.event_id,
            zone_id=event.zone_id,
            disruption_level=event.peak_level,
            payout_pct=_level_to_pct(event.peak_level),
            affected_hours=float(event.affected_hours or 0),
            working_hours=WORKING_HOURS,
            gross_payout_inr=gross,
            cap_applied=cap_applied,
            final_payout_inr=final,
            status="PENDING",
            triggered_at=now,
        )
        db.add(claim)
        created_claims.append(claim)

    db.commit()
    return created_claims


def _level_to_pct(level: str) -> int:
    """Maps disruption level to payout percentage from our locked ladder."""
    return {
        "EXTREME":  100,
        "SEVERE":    75,
        "MODERATE":  50,
        "MILD":      25,
        "NONE":       0,
    }.get(level, 0)


def _get_week_total_paid(
    db: Session,
    policy_id: str,
    reference_dt: datetime,
) -> float:
    """
    Sums all PAID claim final_payout_inr for this policy
    within the same calendar week as reference_dt.
    Used to enforce the weekly payout cap.
    """
    from sqlalchemy import func
    from datetime import timedelta

    # Week boundaries (Mon–Sun)
    ref = reference_dt
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    week_start = ref - timedelta(days=ref.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end   = week_start + timedelta(days=7)

    result = (
        db.query(func.coalesce(func.sum(Claim.final_payout_inr), 0))
        .filter(
            Claim.policy_id   == policy_id,
            Claim.status      == "PAID",
            Claim.triggered_at >= week_start,
            Claim.triggered_at <  week_end,
        )
        .scalar()
    )
    return float(result)