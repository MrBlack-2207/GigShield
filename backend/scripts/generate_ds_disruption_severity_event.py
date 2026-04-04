#!/usr/bin/env python
"""
Generate synthetic training data for ML Use Case 2:
Disruption Severity Estimation.

Dataset:
  ds_disruption_severity_event
Granularity:
  one row per disruption event

Target:
  payout_rate in {0.40, 0.70, 1.00}

Notes:
- event_id and zone_id are identifiers/context only (not model features).
- Uses real events when available, then synthesizes additional rows to keep
  the dataset practically useful for model training.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import statistics
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


RISK_TIER_INDEX = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
EVENT_SIGNAL_TYPES = {"strike", "bandh", "petrol_crisis", "lockdown", "curfew"}
TARGET_EVENTS_PER_ZONE_PER_YEAR = 100


@dataclass
class ZoneCtx:
    zone_id: str
    risk_tier_index: int
    radius_km: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate ds_disruption_severity_event training dataset."
    )
    parser.add_argument("--years", type=int, default=3, help="Number of years to simulate.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output CSV path. Default writes to data/ml_datasets/ds_disruption_severity_event.csv.",
    )
    return parser.parse_args()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
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


def _season_index(month: int) -> int:
    return {"dry": 1, "pre_monsoon": 2, "monsoon": 3, "post_monsoon": 4}[_season_from_month(month)]


def _mean(values: list[float], fallback: float = 0.0) -> float:
    return float(statistics.mean(values)) if values else fallback


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


def _default_output_path() -> Path:
    script_path = Path(__file__).resolve()
    repo_root = _resolve_repo_root(script_path.parent)
    if repo_root:
        return repo_root / "data" / "ml_datasets" / "ds_disruption_severity_event.csv"

    docker_data = Path("/data")
    if docker_data.is_dir():
        return docker_data / "ml_datasets" / "ds_disruption_severity_event.csv"

    raise SystemExit(
        "Could not resolve repository root for default output path. "
        "Set GIGSHIELD_REPO_ROOT or pass --output explicitly."
    )


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


def _payout_rate_from_zdi(zdi_value: float) -> float:
    # README-aligned ladder:
    # 25-50 -> 0.40, 50-75 -> 0.70, 75-100 -> 1.00
    if zdi_value >= 75.0:
        return 1.00
    if zdi_value >= 50.0:
        return 0.70
    return 0.40


def _severity_proxy_zdi(
    peak_zdi_first_hour: float,
    rain_norm_mean: float,
    outage_active_ratio: float,
    event_flag_active_ratio: float,
    noise: float = 0.0,
) -> float:
    """
    Interpretable severity driver:
    - Higher peak ZDI strongly increases severity.
    - Rain-heavy events push severity upward.
    - Outage-heavy events push toward medium/high severity.
    - Event flags add severity uplift.
    """
    rain_uplift = max(0.0, (rain_norm_mean - 45.0) * 0.12)
    outage_uplift = 20.0 * outage_active_ratio
    event_uplift = 30.0 * event_flag_active_ratio

    severity_zdi = peak_zdi_first_hour + rain_uplift + outage_uplift + event_uplift + noise
    return _clamp(severity_zdi, 25.0, 100.0)


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

    readings = (
        db.query(SignalReading)
        .filter(
            SignalReading.zone_id == zone_id,
            SignalReading.recorded_at >= started_at,
            SignalReading.recorded_at < one_hour_end,
        )
        .all()
    )

    rain_vals: list[float] = []
    traffic_vals: list[float] = []
    aqi_vals: list[float] = []
    outage_flags: list[float] = []
    event_total = 0
    event_active = 0

    for r in readings:
        signal_type = str(r.signal_type)
        signal_key = signal_type.lower()
        norm = float(r.normalized_score)
        raw = float(r.raw_value)

        if signal_type == "RAINFALL":
            rain_vals.append(norm)
        elif signal_type == "TRAFFIC":
            traffic_vals.append(norm)
        elif signal_type == "AQI":
            aqi_vals.append(norm)
        elif signal_type == "PLATFORM_OUTAGE":
            outage_flags.append(1.0 if (raw >= 1.0 or norm >= 100.0) else 0.0)
        elif signal_key in EVENT_SIGNAL_TYPES:
            event_total += 1
            if raw >= 1.0 or norm >= 100.0:
                event_active += 1

    season_idx = _season_index(started_at.month)
    start_hour = started_at.hour
    day_of_week = started_at.weekday()

    risk_idx = zone_ctx.risk_tier_index
    season_rain_fallback = {1: 18.0, 2: 40.0, 3: 70.0, 4: 30.0}[season_idx]
    rain_norm_mean = _mean(rain_vals, fallback=season_rain_fallback + 6.0 * risk_idx)
    traffic_norm_mean = _mean(traffic_vals, fallback=28.0 + 5.0 * risk_idx)
    aqi_norm_mean = _mean(aqi_vals, fallback={1: 25.0, 2: 20.0, 3: 15.0, 4: 18.0}[season_idx] + 2.0 * risk_idx)
    outage_active_ratio = _mean(outage_flags, fallback=0.02 + 0.01 * risk_idx)
    event_flag_active_ratio = (
        float(event_active) / float(event_total)
        if event_total > 0
        else 0.0
    )

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
            elapsed_hours = max(
                (zdi_rows[-1].timestamp - zdi_rows[0].timestamp).total_seconds() / 3600.0,
                0.25,
            )
            zdi_rise_rate_first_hour = (zdi_values[-1] - zdi_values[0]) / elapsed_hours
        else:
            zdi_rise_rate_first_hour = 0.0
    else:
        event_count_hint = round(event_flag_active_ratio * 5.0)
        peak_from_event = float(getattr(event, "peak_zdi", 0) or 0)
        peak_zdi_first_hour = _clamp(
            max(
                peak_from_event,
                (
                    0.45 * rain_norm_mean
                    + 0.30 * (outage_active_ratio * 100.0)
                    + 0.15 * traffic_norm_mean
                    + 0.10 * aqi_norm_mean
                    + 8.0 * event_count_hint
                ),
            ),
            25.0,
            100.0,
        )
        zdi_rise_rate_first_hour = (
            2.5
            + 18.0 * outage_active_ratio
            + 5.5 * event_flag_active_ratio
        )

    severity_zdi = _severity_proxy_zdi(
        peak_zdi_first_hour=peak_zdi_first_hour,
        rain_norm_mean=rain_norm_mean,
        outage_active_ratio=outage_active_ratio,
        event_flag_active_ratio=event_flag_active_ratio,
        noise=0.0,
    )
    payout_rate = _payout_rate_from_zdi(severity_zdi)

    return {
        "event_id": str(event.event_id),
        "zone_id": zone_id,
        "season_index": int(season_idx),
        "day_of_week": int(day_of_week),
        "start_hour": int(start_hour),
        "risk_tier_index": int(risk_idx),
        "radius_km": round(zone_ctx.radius_km, 3),
        "rain_norm_mean": round(_clamp(rain_norm_mean, 0.0, 100.0), 4),
        "traffic_norm_mean": round(_clamp(traffic_norm_mean, 0.0, 100.0), 4),
        "aqi_norm_mean": round(_clamp(aqi_norm_mean, 0.0, 100.0), 4),
        "outage_active_ratio": round(_clamp(outage_active_ratio, 0.0, 1.0), 6),
        "event_flag_active_ratio": round(_clamp(event_flag_active_ratio, 0.0, 1.0), 6),
        "peak_zdi_first_hour": round(_clamp(peak_zdi_first_hour, 0.0, 100.0), 4),
        "zdi_rise_rate_first_hour": round(zdi_rise_rate_first_hour, 6),
        "payout_rate": payout_rate,
    }


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
        population=list(range(24)),
        weights=[1, 1, 1, 1, 1, 2, 2, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 4, 3, 2, 2, 1],
        k=1,
    )[0]
    start_dt = datetime(year, month, day, start_hour, 0, 0, tzinfo=timezone.utc)

    season_idx = _season_index(month)
    risk_idx = zone_ctx.risk_tier_index

    rain_base = {1: 18.0, 2: 40.0, 3: 70.0, 4: 30.0}[season_idx]
    rain_norm_mean = _clamp(rain_base + 6.0 * risk_idx + rng.gauss(0.0, 9.0), 0.0, 100.0)

    outage_base = 0.02 + 0.01 * risk_idx
    outage_spike = rng.random() < (0.20 + 0.05 * risk_idx)
    outage_active_ratio = outage_base + (rng.uniform(0.18, 0.48) if outage_spike else rng.uniform(0.0, 0.08))
    outage_active_ratio = _clamp(outage_active_ratio, 0.0, 1.0)

    event_flag_active_ratio = rng.uniform(0.0, 0.05)
    if rng.random() < 0.10:
        event_flag_active_ratio += rng.uniform(0.05, 0.25)
    event_flag_active_ratio = _clamp(event_flag_active_ratio, 0.0, 1.0)

    traffic_norm_mean = _clamp(
        24.0
        + 0.22 * rain_norm_mean
        + 70.0 * outage_active_ratio
        + 35.0 * event_flag_active_ratio
        + rng.gauss(0.0, 7.0),
        0.0,
        100.0,
    )

    aqi_norm_mean = _clamp(
        {1: 26.0, 2: 20.0, 3: 14.0, 4: 18.0}[season_idx]
        + 2.2 * risk_idx
        + rng.gauss(0.0, 3.0),
        0.0,
        100.0,
    )

    peak_zdi_first_hour = _clamp(
        0.45 * rain_norm_mean
        + 0.30 * (outage_active_ratio * 100.0)
        + 0.15 * traffic_norm_mean
        + 0.10 * aqi_norm_mean
        + 22.0 * event_flag_active_ratio
        + rng.gauss(0.0, 5.0),
        25.0,
        100.0,
    )

    zdi_rise_rate_first_hour = (
        3.0
        + 20.0 * outage_active_ratio
        + 6.5 * event_flag_active_ratio
        + 0.04 * rain_norm_mean
        + rng.gauss(0.0, 1.8)
    )

    # Bounded noise keeps target stochastic while preserving interpretable rules.
    severity_noise = _clamp(rng.gauss(0.0, 4.0), -7.0, 7.0)
    severity_zdi = _severity_proxy_zdi(
        peak_zdi_first_hour=peak_zdi_first_hour,
        rain_norm_mean=rain_norm_mean,
        outage_active_ratio=outage_active_ratio,
        event_flag_active_ratio=event_flag_active_ratio,
        noise=severity_noise,
    )
    payout_rate = _payout_rate_from_zdi(severity_zdi)

    return {
        "event_id": f"SYN-SEV-{zone_ctx.zone_id}-{year}-{seq:07d}-{uuid.uuid4().hex[:6]}",
        "zone_id": zone_ctx.zone_id,
        "season_index": int(season_idx),
        "day_of_week": int(start_dt.weekday()),
        "start_hour": int(start_hour),
        "risk_tier_index": int(risk_idx),
        "radius_km": round(zone_ctx.radius_km, 3),
        "rain_norm_mean": round(rain_norm_mean, 4),
        "traffic_norm_mean": round(traffic_norm_mean, 4),
        "aqi_norm_mean": round(aqi_norm_mean, 4),
        "outage_active_ratio": round(outage_active_ratio, 6),
        "event_flag_active_ratio": round(event_flag_active_ratio, 6),
        "peak_zdi_first_hour": round(peak_zdi_first_hour, 4),
        "zdi_rise_rate_first_hour": round(zdi_rise_rate_first_hour, 6),
        "payout_rate": payout_rate,
    }


def _write_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "event_id",
        "zone_id",
        "season_index",
        "day_of_week",
        "start_hour",
        "risk_tier_index",
        "radius_km",
        "rain_norm_mean",
        "traffic_norm_mean",
        "aqi_norm_mean",
        "outage_active_ratio",
        "event_flag_active_ratio",
        "peak_zdi_first_hour",
        "zdi_rise_rate_first_hour",
        "payout_rate",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_metadata(
    output_path: Path,
    years: int,
    seed: int,
    zones_used: int,
    real_rows: int,
    synthetic_rows: int,
) -> Path:
    metadata = {
        "dataset_name": "ds_disruption_severity_event",
        "zones_used": zones_used,
        "rows_generated": real_rows + synthetic_rows,
        "real_rows": real_rows,
        "synthetic_rows": synthetic_rows,
        "seed": seed,
        "years": years,
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
            risk_raw = str(getattr(z, "risk_tier", "MEDIUM") or "MEDIUM").upper()
            zone_map[str(z.zone_id)] = ZoneCtx(
                zone_id=str(z.zone_id),
                risk_tier_index=RISK_TIER_INDEX.get(risk_raw, 1),
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
            if row is not None:
                real_rows.append(row)

        target_total_rows = max(
            len(real_rows),
            len(zone_map) * args.years * TARGET_EVENTS_PER_ZONE_PER_YEAR,
        )
        synthetic_needed = max(0, target_total_rows - len(real_rows))

        synthetic_rows: list[dict] = []
        zone_list = list(zone_map.values())
        for i in range(synthetic_needed):
            z = zone_list[i % len(zone_list)]
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
            years=args.years,
            seed=args.seed,
            zones_used=len(zone_map),
            real_rows=len(real_rows),
            synthetic_rows=len(synthetic_rows),
        )

        print("Dataset generation complete.")
        print(f"output_csv={output_path}")
        print(f"metadata_json={meta_path}")
        print(
            "zones="
            f"{len(zone_map)} real_rows={len(real_rows)} synthetic_rows={len(synthetic_rows)} total_rows={len(rows)}"
        )
        print("Identifier/context columns included: event_id, zone_id (not intended model features).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
