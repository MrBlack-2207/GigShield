from __future__ import annotations

import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.engine.premium_calculator import SEASONAL_DISRUPTION_DAYS
from app.models.signal_reading import SignalReading
from app.models.zone import Zone
from app.models.zone_zdi_log import ZoneZDILog

settings = get_settings()

MODEL_FEATURES = [
    "season_index",
    "week_of_season",
    "risk_tier_index",
    "radius_km",
    "rain_norm_mean",
    "rain_norm_p95",
    "traffic_norm_mean",
    "outage_active_ratio",
    "event_flag_active_ratio",
    "aqi_norm_mean",
    "recent_4week_disruption_days",
    "prev_4week_zdi_mean",
    "prev_4week_zdi_p95",
]

EVENT_SIGNAL_TYPES = {"strike", "bandh", "petrol_crisis", "lockdown", "curfew"}
RISK_TIER_INDEX = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
SEASON_INDEX = {"dry": 1, "pre_monsoon": 2, "monsoon": 3, "post_monsoon": 4}
CORE_SIGNAL_TYPES = ("RAINFALL", "TRAFFIC", "PLATFORM_OUTAGE", "AQI")


@dataclass
class DisruptionFrequencyInferenceResult:
    seasonal_disruption_days: float
    source: str  # ml_prediction | fallback_static
    reason: str | None = None
    model_path: str | None = None

    @property
    def used_ml(self) -> bool:
        return self.source == "ml_prediction"


def _to_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _season_from_month(month: int) -> str:
    if month in (1, 2, 3, 4):
        return "dry"
    if month in (5, 6):
        return "pre_monsoon"
    if month in (7, 8, 9, 10):
        return "monsoon"
    return "post_monsoon"


def _season_start_date(now: datetime, season: str) -> datetime:
    year = now.year
    if season == "dry":
        return now.replace(year=year, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if season == "pre_monsoon":
        return now.replace(year=year, month=5, day=1, hour=0, minute=0, second=0, microsecond=0)
    if season == "monsoon":
        return now.replace(year=year, month=7, day=1, hour=0, minute=0, second=0, microsecond=0)
    return now.replace(year=year, month=11, day=1, hour=0, minute=0, second=0, microsecond=0)


@lru_cache(maxsize=2)
def _load_model_cached(model_path: str):
    path = Path(model_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    with path.open("rb") as f:
        model = pickle.load(f)
    return model, str(path.resolve())


def _fallback_static(season: str, reason: str | None = None) -> DisruptionFrequencyInferenceResult:
    value = float(SEASONAL_DISRUPTION_DAYS.get(season, 1.3))
    return DisruptionFrequencyInferenceResult(
        seasonal_disruption_days=value,
        source="fallback_static",
        reason=reason,
        model_path=None,
    )


def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _safe_percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    return float(pd.Series(values).quantile(q))


def _build_feature_vector(
    db: Session,
    zone_id: str,
    now: datetime,
) -> tuple[dict[str, float], str | None]:
    zone = db.query(Zone).filter(Zone.zone_id == zone_id).first()
    if not zone:
        return {}, f"zone_not_found:{zone_id}"

    risk_tier = str(zone.risk_tier or "MEDIUM").upper()
    risk_tier_index = RISK_TIER_INDEX.get(risk_tier, 1)
    radius_km = float(zone.radius_km or 2.5)

    season = _season_from_month(now.month)
    season_index = SEASON_INDEX[season]
    season_start = _season_start_date(now, season)
    week_of_season = max(1, ((now - season_start).days // 7) + 1)

    lookback_start = now - timedelta(days=settings.DISRUPTION_FREQ_LOOKBACK_DAYS)

    signal_rows: list[SignalReading] = (
        db.query(SignalReading)
        .filter(
            SignalReading.zone_id == zone_id,
            SignalReading.recorded_at >= lookback_start,
            SignalReading.recorded_at < now,
        )
        .all()
    )

    by_type: dict[str, list[SignalReading]] = {t: [] for t in CORE_SIGNAL_TYPES}
    event_rows: list[SignalReading] = []
    for row in signal_rows:
        if row.signal_type in by_type:
            by_type[row.signal_type].append(row)
        if str(row.signal_type).lower() in EVENT_SIGNAL_TYPES:
            event_rows.append(row)

    # Deterministic fallback: require minimum recent core + zdi data.
    min_points = max(1, int(settings.DISRUPTION_FREQ_MIN_POINTS))
    missing_core = [stype for stype, rows in by_type.items() if len(rows) < min_points]
    if missing_core:
        return {}, f"insufficient_core_signal_points:{','.join(missing_core)}"

    zdi_rows: list[ZoneZDILog] = (
        db.query(ZoneZDILog)
        .filter(
            ZoneZDILog.zone_id == zone_id,
            ZoneZDILog.timestamp >= lookback_start,
            ZoneZDILog.timestamp < now,
        )
        .all()
    )
    if len(zdi_rows) < min_points:
        return {}, "insufficient_zdi_points"

    rain_scores = [float(r.normalized_score) for r in by_type["RAINFALL"]]
    traffic_scores = [float(r.normalized_score) for r in by_type["TRAFFIC"]]
    aqi_scores = [float(r.normalized_score) for r in by_type["AQI"]]
    outage_flags = [
        1.0 if (float(r.raw_value) >= 1.0 or int(r.normalized_score) >= 100) else 0.0
        for r in by_type["PLATFORM_OUTAGE"]
    ]

    if event_rows:
        event_active_ratio = _safe_mean(
            [
                1.0 if (float(r.raw_value) >= 1.0 or int(r.normalized_score) >= 100) else 0.0
                for r in event_rows
            ]
        )
    else:
        # Optional event rows may be absent; default to 0 activity.
        event_active_ratio = 0.0

    zdi_values = [float(r.zdi_value) for r in zdi_rows]
    impacted_dates = {
        (r.timestamp.date() if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc).date())
        for r in zdi_rows
        if float(r.zdi_value) >= 25.0
    }

    features = {
        "season_index": float(season_index),
        "week_of_season": float(week_of_season),
        "risk_tier_index": float(risk_tier_index),
        "radius_km": float(radius_km),
        "rain_norm_mean": _safe_mean(rain_scores),
        "rain_norm_p95": _safe_percentile(rain_scores, 0.95),
        "traffic_norm_mean": _safe_mean(traffic_scores),
        "outage_active_ratio": _safe_mean(outage_flags),
        "event_flag_active_ratio": float(event_active_ratio),
        "aqi_norm_mean": _safe_mean(aqi_scores),
        "recent_4week_disruption_days": float(len(impacted_dates) / 4.0),
        "prev_4week_zdi_mean": _safe_mean(zdi_values),
        "prev_4week_zdi_p95": _safe_percentile(zdi_values, 0.95),
    }
    return features, None


def predict_disruption_frequency_days(
    db: Session,
    zone_id: str,
    at_time: datetime | None = None,
) -> DisruptionFrequencyInferenceResult:
    now = _to_utc(at_time)
    season = _season_from_month(now.month)

    features, error = _build_feature_vector(db=db, zone_id=zone_id, now=now)
    if error:
        return _fallback_static(season=season, reason=error)

    try:
        model, resolved_path = _load_model_cached(settings.DISRUPTION_FREQ_MODEL_PATH)
    except Exception as exc:
        return _fallback_static(season=season, reason=f"model_load_failed:{exc}")

    try:
        row = {k: features[k] for k in MODEL_FEATURES}
        feature_df = pd.DataFrame([row], columns=MODEL_FEATURES)
        pred = float(model.predict(feature_df)[0])
        pred = max(settings.DISRUPTION_FREQ_CLIP_MIN, min(settings.DISRUPTION_FREQ_CLIP_MAX, pred))
        return DisruptionFrequencyInferenceResult(
            seasonal_disruption_days=round(pred, 4),
            source="ml_prediction",
            reason=None,
            model_path=resolved_path,
        )
    except Exception as exc:
        return _fallback_static(season=season, reason=f"inference_failed:{exc}")
