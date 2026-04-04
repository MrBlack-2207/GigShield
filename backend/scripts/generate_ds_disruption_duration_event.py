#!/usr/bin/env python
"""
Generate synthetic training data for ML Use Case 3:
Disruption Duration Estimation.

Dataset:
  ds_disruption_duration_event
Granularity:
  one row per disruption event

Output columns:
  event_id, zone_id, season, start_hour, day_of_week,
  early_rain_mean, early_outage_ratio, early_traffic_mean, early_aqi_mean,
  peak_zdi_first_hour, zdi_rise_rate_first_hour, event_flags_active_count_first_hour,
  affected_hours, avg_hours_fraction

Notes:
- event_id and zone_id are identifiers/context only (not model features).
- Uses real events if present, then synthesizes additional rows for practical dataset size.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


EVENT_SIGNAL_TYPES = {"strike", "bandh", "petrol_crisis", "lockdown", "curfew"}
CORE_SIGNAL_TYPES = {"RAINFALL", "PLATFORM_OUTAGE", "TRAFFIC", "AQI"}
RISK_TIER_INDEX = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
TARGET_EVENTS_PER_ZONE_PER_YEAR = 100


@dataclass
class ZoneCtx:
    zone_id: str
    risk_tier: str
    risk_tier_index: int
    radius_km: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate ds_disruption_duration_event training dataset."
    )
    parser.add_argument("--years", type=int, default=3, help="Number of years to simulate.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output CSV path. Default writes to data/ml_datasets/ds_disruption_duration_event.csv.",
    )
    return parser.parse_args()


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _season_from_month(month: int) -> str:
    if month in (1, 2, 3, 4):
        return "dry"
    if month in (5, 6):
        return "pre_monsoon"
    if month in (7, 8, 9, 10):
        return "monsoon"
    return "post_monsoon"


def _default_output_path() -> Path:
    script_path = Path(__file__).resolve()
    repo_root = _resolve_repo_root(script_path.parent)
    if repo_root:
        return repo_root / "data" / "ml_datasets" / "ds_disruption_duration_event.csv"

    docker_data = Path("/data")
    if docker_data.is_dir():
        return docker_data / "ml_datasets" / "ds_disruption_duration_event.csv"

    raise SystemExit(
        "Could not resolve repository root for default output path. "
        "Set GIGSHIELD_REPO_ROOT or pass --output explicitly."
    )


def _candidate_roots(start: Path) -> list[Path]:
    roots: list[Path] = []

    env_root = os.environ.get("GIGSHIELD_REPO_ROOT")
    if env_root:
        roots.append(Path(env_root).expanduser().resolve())

    roots.extend([start] + list(start.parents))

    cwd = Path.cwd().resolve()
    roots.extend([cwd] + list(cwd.parents))

    seen: set[Path] = set()
    ordered: list[Path] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            ordered.append(r)
    return ordered


def _resolve_repo_root(start: Path) -> Path | None:
    for candidate in _candidate_roots(start):
        if (candidate / "backend").is_dir() and (candidate / "data").is_dir():
            return candidate
    return None


def _load_backend():
    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from app.database import SessionLocal  # noqa
    from app.models.disruption_event import DisruptionEvent  # noqa
    from app.models.signal_reading import SignalReading  # noqa
    from app.models.zone import Zone  # noqa
    from app.models.zone_zdi_log import ZoneZDILog  # noqa

    return SessionLocal, Zone, DisruptionEvent, SignalReading, ZoneZDILog


def _mean(values: list[float], fallback: float = 0.0) -> float:
    return float(statistics.mean(values)) if values else fallback


def _p95(values: list[float], fallback: float = 0.0) -> float:
    if not values:
        return fallback
    vals = sorted(values)
    idx = max(0, min(len(vals) - 1, int(0.95 * (len(vals) - 1))))
    return float(vals[idx])


def _duration_rule_interpretable(
    early_rain_mean: float,
    early_outage_ratio: float,
    early_traffic_mean: float,
    event_flags_active_count_first_hour: int,
    season: str,
    start_hour: int,
    rng: random.Random,
) -> float:
    """
    Explicit interpretable duration rule:
    - outage-heavy -> shorter durations
    - rain-heavy -> longer durations
    - event flags -> duration uplift
    - late-night start modifies duration profile
    - bounded noise + clipping
    """
    season_bias = {
        "dry": -0.20,
        "pre_monsoon": 0.25,
        "monsoon": 0.85,
        "post_monsoon": 0.10,
    }[season]

    rain_tail = 0.060 * early_rain_mean
    outage_shortening = 3.1 * early_outage_ratio
    traffic_uplift = 0.012 * early_traffic_mean
    event_uplift = 0.42 * float(event_flags_active_count_first_hour)

    if 0 <= start_hour <= 4:
        time_adjust = -0.35
    elif 5 <= start_hour <= 8:
        time_adjust = 0.05
    elif 9 <= start_hour <= 18:
        time_adjust = 0.22
    else:
        time_adjust = 0.00

    bounded_noise = _clamp(rng.gauss(0.0, 0.30), -0.60, 0.60)

    affected_hours = (
        0.90
        + season_bias
        + rain_tail
        + traffic_uplift
        + event_uplift
        - outage_shortening
        + time_adjust
        + bounded_noise
    )
    return _clamp(affected_hours, 0.25, 10.0)


def _build_real_row(
    db,
    event,
    zone_map: dict[str, ZoneCtx],
    SignalReading,
    ZoneZDILog,
) -> dict | None:
    started_at = _to_utc(getattr(event, "started_at", None))
    if started_at is None:
        return None

    ended_at = _to_utc(getattr(event, "ended_at", None)) or (started_at + timedelta(hours=1))
    one_hour_end = min(started_at + timedelta(hours=1), ended_at)
    if one_hour_end <= started_at:
        one_hour_end = started_at + timedelta(hours=1)

    zone_id = str(event.zone_id)
    zone_ctx = zone_map.get(zone_id)
    if not zone_ctx:
        return None

    season = _season_from_month(started_at.month)
    start_hour = started_at.hour
    day_of_week = started_at.weekday()

    # Core + event signal stats in first hour
    readings = (
        db.query(SignalReading)
        .filter(
            SignalReading.zone_id == zone_id,
            SignalReading.recorded_at >= started_at,
            SignalReading.recorded_at < one_hour_end,
        )
        .all()
    )

    rain_vals, traffic_vals, aqi_vals = [], [], []
    outage_flags = []
    active_event_signals = set()

    for r in readings:
        stype = str(r.signal_type)
        norm = float(r.normalized_score)
        raw = float(r.raw_value)

        if stype == "RAINFALL":
            rain_vals.append(norm)
        elif stype == "TRAFFIC":
            traffic_vals.append(norm)
        elif stype == "AQI":
            aqi_vals.append(norm)
        elif stype == "PLATFORM_OUTAGE":
            outage_flags.append(1.0 if (raw >= 1.0 or norm >= 100.0) else 0.0)
        elif stype.lower() in EVENT_SIGNAL_TYPES:
            if raw >= 1.0 or norm >= 100.0:
                active_event_signals.add(stype.lower())

    early_rain_mean = _mean(rain_vals, fallback=20.0 + (8.0 * zone_ctx.risk_tier_index))
    early_traffic_mean = _mean(traffic_vals, fallback=30.0 + (5.0 * zone_ctx.risk_tier_index))
    early_aqi_mean = _mean(aqi_vals, fallback=18.0 + (3.0 * zone_ctx.risk_tier_index))
    early_outage_ratio = _mean(outage_flags, fallback=0.03 + (0.01 * zone_ctx.risk_tier_index))

    zdi_rows = (
        db.query(ZoneZDILog)
        .filter(
            ZoneZDILog.zone_id == zone_id,
            ZoneZDILog.timestamp >= started_at,
            ZoneZDILog.timestamp < one_hour_end,
        )
        .order_by(ZoneZDILog.timestamp.asc())
        .all()
    )
    zdi_values = [float(z.zdi_value) for z in zdi_rows]
    if zdi_values:
        peak_zdi_first_hour = max(zdi_values)
        if len(zdi_values) >= 2:
            hours = max((zdi_rows[-1].timestamp - zdi_rows[0].timestamp).total_seconds() / 3600.0, 0.25)
            zdi_rise_rate_first_hour = (zdi_values[-1] - zdi_values[0]) / hours
        else:
            zdi_rise_rate_first_hour = 0.0
    else:
        peak_zdi_first_hour = _clamp(
            0.45 * early_rain_mean
            + 0.30 * (early_outage_ratio * 100.0)
            + 0.15 * early_traffic_mean
            + 0.10 * early_aqi_mean
            + 8.0 * len(active_event_signals),
            0.0,
            100.0,
        )
        zdi_rise_rate_first_hour = 0.0

    # Use real affected_hours when available; otherwise infer from timestamps.
    affected_hours_raw = getattr(event, "affected_hours", None)
    if affected_hours_raw is not None:
        affected_hours = float(affected_hours_raw)
    else:
        affected_hours = max((ended_at - started_at).total_seconds() / 3600.0, 0.25)
    affected_hours = _clamp(affected_hours, 0.25, 10.0)

    row = {
        "event_id": str(event.event_id),
        "zone_id": zone_id,
        "season": season,
        "start_hour": int(start_hour),
        "day_of_week": int(day_of_week),
        "early_rain_mean": round(early_rain_mean, 4),
        "early_outage_ratio": round(_clamp(early_outage_ratio, 0.0, 1.0), 6),
        "early_traffic_mean": round(_clamp(early_traffic_mean, 0.0, 100.0), 4),
        "early_aqi_mean": round(_clamp(early_aqi_mean, 0.0, 100.0), 4),
        "peak_zdi_first_hour": round(_clamp(peak_zdi_first_hour, 0.0, 100.0), 4),
        "zdi_rise_rate_first_hour": round(zdi_rise_rate_first_hour, 6),
        "event_flags_active_count_first_hour": int(len(active_event_signals)),
        "affected_hours": round(affected_hours, 4),
        "avg_hours_fraction": round(affected_hours / 10.0, 6),
    }
    return row


def _build_synthetic_row(
    zone_ctx: ZoneCtx,
    sim_years: list[int],
    rng: random.Random,
    seq: int,
) -> dict:
    year = rng.choice(sim_years)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    start_hour = rng.choices(
        population=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
        weights=[
            1, 1, 1, 1, 1, 2, 2, 3, 3, 4, 4, 4,
            4, 4, 4, 4, 4, 5, 5, 4, 3, 2, 2, 1,
        ],
        k=1,
    )[0]
    start_dt = datetime(year, month, day, start_hour, 0, 0, tzinfo=timezone.utc)
    season = _season_from_month(month)

    season_rain_base = {"dry": 18.0, "pre_monsoon": 42.0, "monsoon": 70.0, "post_monsoon": 32.0}[season]
    early_rain_mean = _clamp(season_rain_base + 6.0 * zone_ctx.risk_tier_index + rng.gauss(0.0, 8.5), 0.0, 100.0)

    base_outage = 0.025 + 0.012 * zone_ctx.risk_tier_index
    outage_spike = rng.random() < 0.22
    early_outage_ratio = base_outage + (rng.uniform(0.20, 0.55) if outage_spike else rng.uniform(0.0, 0.08))
    early_outage_ratio = _clamp(early_outage_ratio, 0.0, 1.0)

    early_traffic_mean = _clamp(
        24.0 + 0.18 * early_rain_mean + 45.0 * early_outage_ratio + rng.gauss(0.0, 7.0),
        0.0,
        100.0,
    )
    early_aqi_mean = _clamp(
        {"dry": 26.0, "pre_monsoon": 20.0, "monsoon": 14.0, "post_monsoon": 18.0}[season]
        + 2.5 * zone_ctx.risk_tier_index
        + rng.gauss(0.0, 3.0),
        0.0,
        100.0,
    )

    # Rare event flags; when present they can extend duration.
    if rng.random() < 0.10:
        event_flags_active_count_first_hour = rng.randint(1, 3)
    elif rng.random() < 0.02:
        event_flags_active_count_first_hour = 4
    else:
        event_flags_active_count_first_hour = 0

    # Outage-heavy events have sharper first-hour rise rates.
    zdi_rise_rate_first_hour = (
        4.0
        + 22.0 * early_outage_ratio
        + 0.05 * early_rain_mean
        + 1.8 * event_flags_active_count_first_hour
        + rng.gauss(0.0, 2.0)
    )

    peak_zdi_first_hour = _clamp(
        0.45 * early_rain_mean
        + 0.30 * (early_outage_ratio * 100.0)
        + 0.15 * early_traffic_mean
        + 0.10 * early_aqi_mean
        + 10.0 * event_flags_active_count_first_hour
        + rng.gauss(0.0, 5.0),
        0.0,
        100.0,
    )

    affected_hours = _duration_rule_interpretable(
        early_rain_mean=early_rain_mean,
        early_outage_ratio=early_outage_ratio,
        early_traffic_mean=early_traffic_mean,
        event_flags_active_count_first_hour=event_flags_active_count_first_hour,
        season=season,
        start_hour=start_hour,
        rng=rng,
    )

    return {
        "event_id": f"SYN-{zone_ctx.zone_id}-{year}-{seq:07d}-{uuid.uuid4().hex[:6]}",
        "zone_id": zone_ctx.zone_id,
        "season": season,
        "start_hour": int(start_hour),
        "day_of_week": int(start_dt.weekday()),
        "early_rain_mean": round(early_rain_mean, 4),
        "early_outage_ratio": round(early_outage_ratio, 6),
        "early_traffic_mean": round(early_traffic_mean, 4),
        "early_aqi_mean": round(early_aqi_mean, 4),
        "peak_zdi_first_hour": round(peak_zdi_first_hour, 4),
        "zdi_rise_rate_first_hour": round(zdi_rise_rate_first_hour, 6),
        "event_flags_active_count_first_hour": int(event_flags_active_count_first_hour),
        "affected_hours": round(affected_hours, 4),
        "avg_hours_fraction": round(affected_hours / 10.0, 6),
    }


def _write_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "event_id",
        "zone_id",
        "season",
        "start_hour",
        "day_of_week",
        "early_rain_mean",
        "early_outage_ratio",
        "early_traffic_mean",
        "early_aqi_mean",
        "peak_zdi_first_hour",
        "zdi_rise_rate_first_hour",
        "event_flags_active_count_first_hour",
        "affected_hours",
        "avg_hours_fraction",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_metadata(
    output_path: Path,
    years_simulated: int,
    row_count: int,
    zone_count: int,
    seed: int,
) -> Path:
    metadata = {
        "dataset_name": "ds_disruption_duration_event",
        "years_simulated": years_simulated,
        "row_count": row_count,
        "zone_count": zone_count,
        "seed_used": seed,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "csv_file": str(output_path),
    }
    meta_path = output_path.with_suffix(".metadata.json")
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return meta_path


def main() -> int:
    args = parse_args()
    if args.years <= 0:
        raise SystemExit("--years must be > 0")

    rng = random.Random(args.seed)
    output_path = Path(args.output).resolve() if args.output else _default_output_path().resolve()

    SessionLocal, Zone, DisruptionEvent, SignalReading, ZoneZDILog = _load_backend()
    db = SessionLocal()
    try:
        zones_db = db.query(Zone).order_by(Zone.zone_id.asc()).all()
        if not zones_db:
            raise SystemExit("No zones found in database.")

        zone_map: dict[str, ZoneCtx] = {}
        for z in zones_db:
            risk = str(getattr(z, "risk_tier", "MEDIUM") or "MEDIUM").upper()
            zone_map[str(z.zone_id)] = ZoneCtx(
                zone_id=str(z.zone_id),
                risk_tier=risk,
                risk_tier_index=RISK_TIER_INDEX.get(risk, 1),
                radius_km=float(getattr(z, "radius_km", 2.5) or 2.5),
            )

        now_year = datetime.now(timezone.utc).year
        sim_years = [now_year - args.years + 1 + i for i in range(args.years)]
        min_year = min(sim_years)
        max_year = max(sim_years)

        real_events = (
            db.query(DisruptionEvent)
            .filter(DisruptionEvent.started_at.isnot(None))
            .all()
        )
        real_rows: list[dict] = []
        for ev in real_events:
            started = _to_utc(getattr(ev, "started_at", None))
            if started is None:
                continue
            if started.year < min_year or started.year > max_year:
                continue
            row = _build_real_row(
                db=db,
                event=ev,
                zone_map=zone_map,
                SignalReading=SignalReading,
                ZoneZDILog=ZoneZDILog,
            )
            if row:
                real_rows.append(row)

        # Ensure practical dataset size even when real events are sparse.
        target_total_rows = max(
            len(real_rows),
            len(zone_map) * args.years * TARGET_EVENTS_PER_ZONE_PER_YEAR,
        )
        synthetic_needed = max(0, target_total_rows - len(real_rows))

        synthetic_rows: list[dict] = []
        zone_list = list(zone_map.values())
        for i in range(synthetic_needed):
            z = zone_list[i % len(zone_list)] if zone_list else None
            if z is None:
                break
            synthetic_rows.append(
                _build_synthetic_row(
                    zone_ctx=z,
                    sim_years=sim_years,
                    rng=rng,
                    seq=i + 1,
                )
            )

        rows = real_rows + synthetic_rows
        rng.shuffle(rows)

        _write_csv(rows, output_path)
        meta_path = _write_metadata(
            output_path=output_path,
            years_simulated=args.years,
            row_count=len(rows),
            zone_count=len(zone_map),
            seed=args.seed,
        )

        print("Dataset generation complete.")
        print(f"output_csv={output_path}")
        print(f"metadata_json={meta_path}")
        print(f"zones={len(zone_map)} real_rows={len(real_rows)} synthetic_rows={len(synthetic_rows)} total_rows={len(rows)}")
        print("Identifiers/context columns included: event_id, zone_id (not intended model features).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
