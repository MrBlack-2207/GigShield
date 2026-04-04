from datetime import datetime, timedelta, timezone
import math

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.claim import Claim
from app.models.disruption_event import DisruptionEvent
from app.models.policy import Policy
from app.models.signal_reading import SignalReading
from app.models.zone import Zone
from app.models.zone_zdi_log import ZoneZDILog
from app.services.audit_service import write_audit
from app.services.disruption_duration_inference import predict_disruption_duration
from app.services.disruption_severity_inference import predict_disruption_severity
from app.services.policy_service import (
    is_policy_payout_eligible,
    sync_policy_status_in_flow,
)
from app.services.zdi_log_service import get_affected_hours

settings = get_settings()

WORKING_HOURS = settings.WORKING_HOURS_PER_DAY
COVERAGE_RATIO = settings.COVERAGE_RATIO
EVENT_SIGNAL_TYPES = {"strike", "bandh", "petrol_crisis", "lockdown", "curfew"}
RISK_TIER_INDEX = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def compute_payout(
    income_tier: int,
    payout_rate: float,
    affected_hours: float,
    weekly_payout_cap: float,
    week_total_paid_so_far: float,
) -> tuple[float, float, bool]:
    """
    EventPayout =
        DailyIncome x CoverageRatio x PayoutRate x (AffectedHours / WorkingHours)

    Returns (gross_payout, final_payout, cap_applied).
    final_payout is capped at (weekly_payout_cap - already_paid_this_week).
    """
    gross = (
        payout_rate
        * (affected_hours / WORKING_HOURS)
        * income_tier
        * COVERAGE_RATIO
    )
    gross = round(gross, 2)

    remaining_cap = max(0.0, float(weekly_payout_cap) - week_total_paid_so_far)
    final = round(min(gross, remaining_cap), 2)
    cap_applied = final < gross

    return gross, final, cap_applied


def trigger_claims_for_event(
    db: Session,
    event: DisruptionEvent,
) -> list[Claim]:
    """
    Called immediately after a DisruptionEvent is closed.

    1. Finds policies in the affected zone.
    2. Applies lifecycle eligibility using policy fields:
       status, tenure window, billing due, cooldown.
    3. Computes affected_hours from zone_zdi_logs for the event window.
    4. Computes payout_rate from max_zdi in the same window:
         25-50 => 0.40, 50-75 => 0.70, 75-100 => 1.00
    5. Creates Claim rows with status=PENDING.
    6. Returns the list of created claims for the fraud checker.
    """
    now = datetime.now(timezone.utc)

    event_start = _to_utc(event.started_at)
    event_end = _to_utc(event.ended_at or now)
    if event_end <= event_start:
        event_end = event_start + timedelta(minutes=15)

    window_stats = get_affected_hours(
        db=db,
        zone_id=event.zone_id,
        start_time=event_start,
        end_time=event_end,
    )
    deterministic_affected_hours = float(window_stats["affected_hours"])
    max_zdi = float(window_stats["max_zdi"])
    fallback_payout_rate = _payout_rate_from_max_zdi(max_zdi)
    duration_features = _build_duration_features(
        db=db,
        zone_id=event.zone_id,
        event_start=event_start,
        event_end=event_end,
        deterministic_affected_hours=deterministic_affected_hours,
        max_zdi=max_zdi,
    )
    severity_features = _build_severity_features(
        db=db,
        zone_id=event.zone_id,
        duration_features=duration_features,
    )
    severity_prediction = predict_disruption_severity(severity_features)
    payout_rate, payout_rate_source, payout_rate_error, ml_payout_rate = _resolve_payout_rate_source(
        severity_prediction=severity_prediction,
        fallback_payout_rate=fallback_payout_rate,
    )
    payout_pct = int(round(payout_rate * 100))
    disruption_level = _disruption_level_from_zdi(max_zdi)

    duration_prediction = predict_disruption_duration(duration_features)
    affected_hours, affected_hours_source, duration_error, ml_affected_hours = _resolve_affected_hours_source(
        duration_prediction=duration_prediction,
        deterministic_affected_hours=deterministic_affected_hours,
    )

    # Persist transparency so final source is visible outside in-memory objects.
    write_audit(
        db=db,
        event_type="AFFECTED_HOURS_SELECTED",
        entity_type="DisruptionEvent",
        entity_id=event.event_id,
        zone_id=event.zone_id,
        payload={
            "event_id": event.event_id,
            "affected_hours_used": round(affected_hours, 2),
            "affected_hours_source": affected_hours_source,
            "deterministic_affected_hours": round(deterministic_affected_hours, 2),
            "ml_affected_hours": ml_affected_hours,
            "duration_inference_error": duration_error,
            "max_zdi_in_window": round(max_zdi, 2),
        },
        is_mocked=True,
    )
    write_audit(
        db=db,
        event_type="PAYOUT_RATE_SELECTED",
        entity_type="DisruptionEvent",
        entity_id=event.event_id,
        zone_id=event.zone_id,
        payload={
            "event_id": event.event_id,
            "payout_rate_used": round(payout_rate, 2),
            "payout_rate_source": payout_rate_source,
            "fallback_zdi_ladder_rate": round(fallback_payout_rate, 2),
            "ml_payout_rate": ml_payout_rate,
            "severity_inference_error": payout_rate_error,
            "max_zdi_in_window": round(max_zdi, 2),
        },
        is_mocked=True,
    )

    candidate_policies: list[Policy] = (
        db.query(Policy)
        .filter(
            Policy.zone_id == event.zone_id,
        )
        .all()
    )

    created_claims: list[Claim] = []

    for policy in candidate_policies:
        effective_status = sync_policy_status_in_flow(db, policy, now)
        if effective_status in {"cancelled", "expired"}:
            continue
        if not is_policy_payout_eligible(policy, now):
            continue

        # Compute how much has already been paid this week.
        week_paid = _get_week_total_paid(db, policy.policy_id, event_start)

        # Enforce weekly cap rule.
        configured_weekly_cap = round(float(policy.income_tier) * COVERAGE_RATIO, 2)
        stored_weekly_cap = float(policy.weekly_payout_cap or configured_weekly_cap)
        effective_weekly_cap = min(stored_weekly_cap, configured_weekly_cap)

        gross, final, cap_applied = compute_payout(
            income_tier=policy.income_tier,
            payout_rate=payout_rate,
            affected_hours=affected_hours,
            weekly_payout_cap=effective_weekly_cap,
            week_total_paid_so_far=week_paid,
        )

        if final <= 0 or payout_rate <= 0.0 or affected_hours <= 0.0:
            continue

        claim = Claim(
            policy_id=policy.policy_id,
            worker_id=policy.worker_id,
            disruption_event_id=event.event_id,
            zone_id=event.zone_id,
            disruption_level=disruption_level,
            payout_pct=payout_pct,
            affected_hours=affected_hours,
            working_hours=WORKING_HOURS,
            gross_payout_inr=gross,
            cap_applied=cap_applied,
            final_payout_inr=final,
            status="PENDING",
            triggered_at=now,
        )

        # Transparency fields available in returned claim objects.
        claim.max_zdi_used = round(max_zdi, 2)
        claim.payout_rate_applied = payout_rate
        claim.payout_rate_used = payout_rate
        claim.payout_rate_source = payout_rate_source
        claim.affected_hours_used = affected_hours
        claim.affected_hours_source = affected_hours_source

        db.add(claim)
        created_claims.append(claim)

    db.commit()
    return created_claims


def _payout_rate_from_max_zdi(max_zdi: float) -> float:
    """
    Required payout-rate ladder:
      ZDI 25-50   -> 0.40
      ZDI 50-75   -> 0.70
      ZDI 75-100  -> 1.00
    """
    if max_zdi >= 75.0:
        return 1.00
    if max_zdi >= 50.0:
        return 0.70
    if max_zdi >= 25.0:
        return 0.40
    return 0.0


def _disruption_level_from_zdi(zdi: float) -> str:
    if zdi >= 85.0:
        return "EXTREME"
    if zdi >= 65.0:
        return "SEVERE"
    if zdi >= 45.0:
        return "MODERATE"
    if zdi >= 25.0:
        return "MILD"
    return "NONE"


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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

    ref = reference_dt
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    week_start = ref - timedelta(days=ref.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)

    result = (
        db.query(func.coalesce(func.sum(Claim.final_payout_inr), 0))
        .filter(
            Claim.policy_id == policy_id,
            Claim.status == "PAID",
            Claim.triggered_at >= week_start,
            Claim.triggered_at < week_end,
        )
        .scalar()
    )
    return float(result)


def _resolve_affected_hours_source(
    duration_prediction: dict,
    deterministic_affected_hours: float,
) -> tuple[float, str, str | None, float | None]:
    """
    Prefer ML-predicted affected_hours only if payload is usable.
    Otherwise, deterministically fall back to ZDI-log affected_hours.
    """
    used = max(0.0, float(deterministic_affected_hours))
    source = "fallback_zdi_logs"
    error: str | None = None
    ml_value: float | None = None

    if not isinstance(duration_prediction, dict):
        return used, source, "invalid_inference_payload", ml_value

    raw_candidate = duration_prediction.get("affected_hours")
    source_raw = str(duration_prediction.get("source", "")).strip().lower()
    reported_error = duration_prediction.get("error")

    try:
        if raw_candidate is not None:
            ml_value = float(raw_candidate)
    except (TypeError, ValueError):
        ml_value = None

    valid_ml_hours = (
        source_raw == "ml"
        and ml_value is not None
        and math.isfinite(ml_value)
        and ml_value > 0.0
    )
    if valid_ml_hours:
        return ml_value, "ml", None, ml_value

    if reported_error:
        error = str(reported_error)
    elif source_raw != "ml":
        error = f"duration_inference_source={source_raw or 'unknown'}"
    else:
        error = "invalid_ml_affected_hours"
    return used, source, error, ml_value


def _resolve_payout_rate_source(
    severity_prediction: dict,
    fallback_payout_rate: float,
) -> tuple[float, str, str | None, float | None]:
    """
    Prefer ML payout_rate only if it maps cleanly to business-allowed rates.
    Otherwise, use deterministic ZDI-ladder fallback.
    """
    fallback = float(fallback_payout_rate)
    source = "fallback_zdi_ladder"
    error: str | None = None
    ml_value: float | None = None

    if not isinstance(severity_prediction, dict):
        return fallback, source, "invalid_inference_payload", ml_value

    raw_pred = severity_prediction.get("payout_rate")
    source_raw = str(severity_prediction.get("source", "")).strip().lower()
    reported_error = severity_prediction.get("error")

    try:
        if raw_pred is not None:
            ml_value = float(raw_pred)
    except (TypeError, ValueError):
        ml_value = None

    valid_ml_rate = (
        source_raw == "ml"
        and ml_value is not None
        and math.isfinite(ml_value)
        and ml_value in {0.40, 0.70, 1.00}
    )
    if valid_ml_rate:
        return ml_value, "ml", None, ml_value

    if reported_error:
        error = str(reported_error)
    elif source_raw != "ml":
        error = f"severity_inference_source={source_raw or 'unknown'}"
    else:
        error = "invalid_ml_payout_rate"
    return fallback, source, error, ml_value


def _build_duration_features(
    db: Session,
    zone_id: str,
    event_start: datetime,
    event_end: datetime,
    deterministic_affected_hours: float,
    max_zdi: float,
) -> dict:
    """
    Build a conservative feature vector for disruption duration inference.
    """
    first_hour_end = min(event_start + timedelta(hours=1), event_end)
    if first_hour_end <= event_start:
        first_hour_end = event_start + timedelta(hours=1)

    readings = (
        db.query(SignalReading)
        .filter(
            SignalReading.zone_id == zone_id,
            SignalReading.recorded_at >= event_start,
            SignalReading.recorded_at < first_hour_end,
        )
        .all()
    )

    rain_vals: list[float] = []
    traffic_vals: list[float] = []
    aqi_vals: list[float] = []
    outage_flags: list[float] = []
    active_event_flags: set[str] = set()

    for reading in readings:
        signal_type = str(reading.signal_type)
        signal_key = signal_type.lower()
        normalized = float(reading.normalized_score)
        raw = float(reading.raw_value)

        if signal_type == "RAINFALL":
            rain_vals.append(normalized)
        elif signal_type == "TRAFFIC":
            traffic_vals.append(normalized)
        elif signal_type == "AQI":
            aqi_vals.append(normalized)
        elif signal_type == "PLATFORM_OUTAGE":
            outage_flags.append(1.0 if (raw >= 1.0 or normalized >= 100.0) else 0.0)
        elif signal_key in EVENT_SIGNAL_TYPES and (raw >= 1.0 or normalized >= 100.0):
            active_event_flags.add(signal_key)

    zdi_rows = (
        db.query(ZoneZDILog)
        .filter(
            ZoneZDILog.zone_id == zone_id,
            ZoneZDILog.timestamp >= event_start,
            ZoneZDILog.timestamp < first_hour_end,
        )
        .order_by(ZoneZDILog.timestamp.asc())
        .all()
    )
    zdi_values = [float(row.zdi_value) for row in zdi_rows]

    if zdi_values:
        peak_zdi_first_hour = max(zdi_values)
        if len(zdi_values) >= 2:
            elapsed_hours = max(
                (zdi_rows[-1].timestamp - zdi_rows[0].timestamp).total_seconds() / 3600.0,
                0.25,
            )
            zdi_rise_rate_first_hour = (zdi_values[-1] - zdi_values[0]) / elapsed_hours
        else:
            zdi_rise_rate_first_hour = 0.0
    else:
        peak_zdi_first_hour = max(0.0, float(max_zdi))
        zdi_rise_rate_first_hour = 0.0

    working_hours = float(WORKING_HOURS) if float(WORKING_HOURS) > 0 else 10.0
    avg_hours_fraction_proxy = max(0.0, float(deterministic_affected_hours)) / working_hours
    season_index = _season_index_from_month(event_start.month)

    return {
        "season_index": season_index,
        "start_hour": int(event_start.hour),
        "day_of_week": int(event_start.weekday()),
        "early_rain_mean": round(_mean_or_default(rain_vals, 0.0), 4),
        "early_outage_ratio": round(_mean_or_default(outage_flags, 0.0), 6),
        "early_traffic_mean": round(_mean_or_default(traffic_vals, 0.0), 4),
        "early_aqi_mean": round(_mean_or_default(aqi_vals, 0.0), 4),
        "peak_zdi_first_hour": round(max(0.0, peak_zdi_first_hour), 4),
        "zdi_rise_rate_first_hour": round(zdi_rise_rate_first_hour, 6),
        "event_flags_active_count_first_hour": int(len(active_event_flags)),
        # Compatibility with existing duration training script feature expectations.
        "avg_hours_fraction": round(avg_hours_fraction_proxy, 6),
    }


def _build_severity_features(
    db: Session,
    zone_id: str,
    duration_features: dict,
) -> dict:
    zone = db.query(Zone).filter(Zone.zone_id == zone_id).first()
    risk_tier_raw = str(getattr(zone, "risk_tier", "MEDIUM") or "MEDIUM").upper() if zone else "MEDIUM"
    risk_tier_index = RISK_TIER_INDEX.get(risk_tier_raw, 1)
    radius_km = float(getattr(zone, "radius_km", 2.5) or 2.5) if zone else 2.5

    active_flags = int(duration_features.get("event_flags_active_count_first_hour", 0) or 0)
    event_flag_active_ratio = max(0.0, min(1.0, active_flags / float(len(EVENT_SIGNAL_TYPES))))

    return {
        "season_index": float(duration_features.get("season_index", 1)),
        "day_of_week": float(duration_features.get("day_of_week", 0)),
        "start_hour": float(duration_features.get("start_hour", 0)),
        "risk_tier_index": float(risk_tier_index),
        "radius_km": float(radius_km),
        "rain_norm_mean": float(duration_features.get("early_rain_mean", 0.0)),
        "traffic_norm_mean": float(duration_features.get("early_traffic_mean", 0.0)),
        "aqi_norm_mean": float(duration_features.get("early_aqi_mean", 0.0)),
        "outage_active_ratio": float(duration_features.get("early_outage_ratio", 0.0)),
        "event_flag_active_ratio": float(event_flag_active_ratio),
        "peak_zdi_first_hour": float(duration_features.get("peak_zdi_first_hour", 0.0)),
        "zdi_rise_rate_first_hour": float(duration_features.get("zdi_rise_rate_first_hour", 0.0)),
    }


def _mean_or_default(values: list[float], default: float) -> float:
    if not values:
        return float(default)
    return float(sum(values) / len(values))


def _season_index_from_month(month: int) -> int:
    if month in (1, 2, 3, 4):
        return 1
    if month in (5, 6):
        return 2
    if month in (7, 8, 9, 10):
        return 3
    return 4

