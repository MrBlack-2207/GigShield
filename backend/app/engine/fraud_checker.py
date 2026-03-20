# gigshield/backend/app/engine/fraud_checker.py

from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.claim  import Claim
from app.models.policy import Policy


# ── Fraud rule thresholds ─────────────────────────────────────────────────────
MAX_CLAIMS_ROLLING_7_DAYS = 3      # R2: more than this in 7 days → flag
ANOMALY_STD_MULTIPLIER    = 2.5    # R4: claim > 2.5σ above worker history → flag


def run_fraud_checks(db: Session, claim: Claim) -> tuple[float, bool]:
    """
    Runs 4 fraud checks against a PENDING claim.
    Returns (fraud_score 0.0–1.0, fraud_flag bool).

    fraud_score is additive across rules:
        R1 policy age   → +0.40
        R2 claim freq   → +0.30
        R3 zone mismatch→ +0.20  (placeholder — needs GPS in production)
        R4 anomaly amt  → +0.10

    fraud_flag = True when fraud_score >= 0.40
    (a single hard rule firing is enough to flag for review)
    """
    score = 0.0
    flags: list[str] = []

    policy: Policy = db.query(Policy).filter(
        Policy.policy_id == claim.policy_id
    ).first()

    # ── R1: Policy age < 48 hours ─────────────────────────────────────────
    # Catches workers who buy policy right after disruption starts
    if policy and policy.lookback_exclusion_until:
        exclusion = policy.lookback_exclusion_until
        if exclusion.tzinfo is None:
            exclusion = exclusion.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if now < exclusion:
            score += 0.40
            flags.append("R1_POLICY_TOO_NEW")

    # ── R2: More than 3 claims in rolling 7 days ─────────────────────────
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_claims  = (
        db.query(Claim)
        .filter(
            Claim.worker_id    == claim.worker_id,
            Claim.triggered_at >= seven_days_ago,
            Claim.status.notin_(["REJECTED"]),
        )
        .count()
    )
    if recent_claims > MAX_CLAIMS_ROLLING_7_DAYS:
        score += 0.30
        flags.append("R2_HIGH_CLAIM_FREQUENCY")

    # ── R3: Zone mismatch ─────────────────────────────────────────────────
    # In production: compare claim.zone_id against worker GPS at trigger time
    # In demo: always passes (no GPS data available in mock)
    # score += 0.20 when zone mismatch detected
    # flags.append("R3_ZONE_MISMATCH")

    # ── R4: Claim amount > 2.5σ above worker's historical average ─────────
    past_claims = (
        db.query(Claim)
        .filter(
            Claim.worker_id == claim.worker_id,
            Claim.status    == "PAID",
        )
        .all()
    )
    if len(past_claims) >= 5:
        amounts = [float(c.final_payout_inr) for c in past_claims]
        mean    = sum(amounts) / len(amounts)
        std     = (sum((a - mean) ** 2 for a in amounts) / len(amounts)) ** 0.5
        if std > 0 and float(claim.final_payout_inr) > mean + ANOMALY_STD_MULTIPLIER * std:
            score += 0.10
            flags.append("R4_AMOUNT_ANOMALY")

    score      = round(min(score, 1.0), 4)
    fraud_flag = score >= 0.40

    return score, fraud_flag