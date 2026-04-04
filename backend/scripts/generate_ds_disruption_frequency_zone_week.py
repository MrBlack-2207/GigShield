#!/usr/bin/env python
"""
Generate synthetic training data for ML Use Case 1:
Disruption Frequency Estimation.

Dataset:
  ds_disruption_frequency_zone_week
Granularity:
  one row per zone_id + year + week_of_year

Output:
  - CSV: ds_disruption_frequency_zone_week.csv
  - Metadata JSON next to CSV
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path


RISK_TIER_TO_INDEX = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
SEASON_TO_INDEX = {"dry": 1, "pre_monsoon": 2, "monsoon": 3, "post_monsoon": 4}


@dataclass
class ZoneRuntimeState:
    disruption_hist: deque[float]
    zdi_mean_hist: deque[float]
    zdi_p95_hist: deque[float]
    prev_aqi_mean: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate ds_disruption_frequency_zone_week synthetic dataset."
    )
    parser.add_argument("--years", type=int, default=3, help="Number of years to simulate.")
    parser.add_argument(
        "--start-year",
        type=int,
        default=None,
        help="Start year (inclusive). Defaults to current_year - years + 1.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output CSV path. Defaults to <repo>/data/ml_datasets/ds_disruption_frequency_zone_week.csv.",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="If Zone.is_active exists, filter to active zones only.",
    )
    return parser.parse_args()


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def season_from_month(month: int) -> str:
    if month in (1, 2, 3, 4):
        return "dry"
    if month in (5, 6):
        return "pre_monsoon"
    if month in (7, 8, 9, 10):
        return "monsoon"
    return "post_monsoon"


def iso_weeks_in_year(year: int) -> int:
    return date(year, 12, 28).isocalendar().week


def mean_or_zero(values: deque[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def derive_baseline_from_zone(
    risk_tier_index: int,
    radius_km: float,
    season: str,
) -> float:
    risk_base = {0: 0.7, 1: 1.1, 2: 1.6}.get(risk_tier_index, 1.1)
    season_mult = {"dry": 0.75, "pre_monsoon": 1.10, "monsoon": 1.60, "post_monsoon": 0.95}[season]
    radius_mult = clamp(1.0 + (radius_km - 2.5) * 0.08, 0.85, 1.20)
    return clamp(risk_base * season_mult * radius_mult, 0.3, 3.8)


def seasonal_baseline_if_available(zone_obj: object, season: str) -> float | None:
    raw = getattr(zone_obj, "seasonal_disruption_days", None)
    if not isinstance(raw, dict):
        return None
    value = raw.get(season)
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def init_backend(root_hint: Path):
    if (root_hint / "app").is_dir():
        backend_path = root_hint
    else:
        backend_path = root_hint / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from app.database import SessionLocal  # noqa
    from app.models.zone import Zone  # noqa

    return SessionLocal, Zone


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


def resolve_repo_root(start: Path) -> Path | None:
    for candidate in _candidate_roots(start):
        if (candidate / "backend").is_dir() and (candidate / "data").is_dir():
            return candidate
    return None


def resolve_default_output_path(start: Path) -> Path:
    repo_root = resolve_repo_root(start)
    if repo_root:
        return repo_root / "data" / "ml_datasets" / "ds_disruption_frequency_zone_week.csv"

    docker_data = Path("/data")
    if docker_data.is_dir():
        return docker_data / "ml_datasets" / "ds_disruption_frequency_zone_week.csv"

    raise SystemExit(
        "Could not resolve repository root for default output path. "
        "Set GIGSHIELD_REPO_ROOT or pass --output explicitly."
    )


def build_rows(zones: list[object], years: list[int], rng: random.Random) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    season_week_counter: dict[tuple[int, str], int] = defaultdict(int)

    state_by_zone: dict[str, ZoneRuntimeState] = {}
    for zone in zones:
        zid = str(getattr(zone, "zone_id"))
        state_by_zone[zid] = ZoneRuntimeState(
            disruption_hist=deque(maxlen=4),
            zdi_mean_hist=deque(maxlen=4),
            zdi_p95_hist=deque(maxlen=4),
            prev_aqi_mean=rng.uniform(12.0, 28.0),
        )

    for year in years:
        weeks = iso_weeks_in_year(year)
        for week in range(1, weeks + 1):
            monday = date.fromisocalendar(year, week, 1)
            season = season_from_month(monday.month)
            season_index = SEASON_TO_INDEX[season]
            season_week_counter[(year, season)] += 1
            week_of_season = season_week_counter[(year, season)]

            for zone in zones:
                zone_id = str(getattr(zone, "zone_id"))
                risk_raw = str(getattr(zone, "risk_tier", "MEDIUM") or "MEDIUM").upper()
                risk_tier_index = RISK_TIER_TO_INDEX.get(risk_raw, 1)
                radius_km = float(getattr(zone, "radius_km", 2.5) or 2.5)

                state = state_by_zone[zone_id]
                recent_4week_disruption_days = mean_or_zero(state.disruption_hist)
                prev_4week_zdi_mean = mean_or_zero(state.zdi_mean_hist)
                prev_4week_zdi_p95 = mean_or_zero(state.zdi_p95_hist)

                baseline = seasonal_baseline_if_available(zone, season)
                if baseline is None:
                    baseline = derive_baseline_from_zone(risk_tier_index, radius_km, season)

                # Event weeks are uncommon but can elevate disruption burden.
                event_prob = {"dry": 0.03, "pre_monsoon": 0.05, "monsoon": 0.08, "post_monsoon": 0.04}[season]
                event_week = rng.random() < event_prob

                # Weekly simulated signal aggregates (0-100 norm where applicable).
                rain_base = {"dry": 18.0, "pre_monsoon": 38.0, "monsoon": 68.0, "post_monsoon": 30.0}[season]
                rain_base += {-1: 0.0, 0: -4.0, 1: 0.0, 2: 5.0}.get(risk_tier_index, 0.0)
                rain_norm_mean = clamp(rain_base + rng.gauss(0.0, 6.0), 0.0, 100.0)
                rain_norm_p95 = clamp(rain_norm_mean + rng.uniform(10.0, 28.0), 0.0, 100.0)

                event_flag_active_ratio = rng.uniform(0.00, 0.04)
                if event_week:
                    event_flag_active_ratio += rng.uniform(0.04, 0.13)
                event_flag_active_ratio = clamp(event_flag_active_ratio, 0.0, 0.25)

                outage_base = 0.015 + (0.005 * risk_tier_index) + rng.uniform(0.0, 0.02)
                if event_week:
                    outage_base += rng.uniform(0.02, 0.07)
                outage_active_ratio = clamp(outage_base, 0.0, 0.30)

                traffic_norm_mean = clamp(
                    24.0
                    + 0.22 * rain_norm_mean
                    + 90.0 * outage_active_ratio
                    + rng.gauss(0.0, 5.0),
                    0.0,
                    100.0,
                )

                aqi_season_base = {"dry": 24.0, "pre_monsoon": 20.0, "monsoon": 14.0, "post_monsoon": 18.0}[season]
                aqi_target = clamp(aqi_season_base + (2.0 * risk_tier_index), 0.0, 100.0)
                aqi_norm_mean = clamp(
                    0.70 * state.prev_aqi_mean + 0.30 * aqi_target + rng.gauss(0.0, 2.0),
                    0.0,
                    100.0,
                )
                state.prev_aqi_mean = aqi_norm_mean

                # Simulated weekly ZDI stats for rolling features.
                zdi_core = (
                    0.45 * (0.6 * (rain_norm_mean / 100.0) + 0.4 * (rain_norm_p95 / 100.0))
                    + 0.30 * min(1.0, outage_active_ratio / 0.20)
                    + 0.15 * (traffic_norm_mean / 100.0)
                    + 0.10 * (aqi_norm_mean / 100.0)
                )
                zdi_event_boost = 0.14 * min(1.0, event_flag_active_ratio / 0.20)
                zdi_mean = clamp(100.0 * (zdi_core + zdi_event_boost) + rng.gauss(0.0, 3.0), 0.0, 100.0)
                zdi_p95 = clamp(
                    zdi_mean + 0.35 * (rain_norm_p95 - rain_norm_mean) + (12.0 if event_week else 0.0) + rng.gauss(0.0, 4.0),
                    0.0,
                    100.0,
                )

                # Interpretable target generation from weekly signal burden + rolling history.
                burden_signal = (
                    0.44 * (0.55 * (rain_norm_mean / 100.0) + 0.45 * (rain_norm_p95 / 100.0))
                    + 0.26 * min(1.0, outage_active_ratio / 0.20)
                    + 0.15 * min(1.0, event_flag_active_ratio / 0.20)
                    + 0.10 * (traffic_norm_mean / 100.0)
                    + 0.05 * (aqi_norm_mean / 100.0)
                )
                rolling_component = 0.28 * (recent_4week_disruption_days / 4.0) + 0.12 * (prev_4week_zdi_mean / 100.0)
                baseline_component = 0.18 * (baseline / 4.0)
                noise = clamp(rng.gauss(0.0, 0.22), -0.45, 0.45)

                seasonal_disruption_days = 4.0 * (0.62 * burden_signal + 0.23 * rolling_component + 0.15 * baseline_component)
                seasonal_disruption_days = clamp(seasonal_disruption_days + noise, 0.0, 4.0)
                seasonal_disruption_days = round(seasonal_disruption_days, 3)

                row = {
                    "zone_id": zone_id,
                    "year": year,
                    "week_of_year": week,
                    "season_index": season_index,
                    "week_of_season": week_of_season,
                    "risk_tier_index": risk_tier_index,
                    "radius_km": round(radius_km, 3),
                    "rain_norm_mean": round(rain_norm_mean, 3),
                    "rain_norm_p95": round(rain_norm_p95, 3),
                    "traffic_norm_mean": round(traffic_norm_mean, 3),
                    "outage_active_ratio": round(outage_active_ratio, 5),
                    "event_flag_active_ratio": round(event_flag_active_ratio, 5),
                    "aqi_norm_mean": round(aqi_norm_mean, 3),
                    "recent_4week_disruption_days": round(recent_4week_disruption_days, 3),
                    "prev_4week_zdi_mean": round(prev_4week_zdi_mean, 3),
                    "prev_4week_zdi_p95": round(prev_4week_zdi_p95, 3),
                    "seasonal_disruption_days": seasonal_disruption_days,
                }
                rows.append(row)

                # Update rolling windows with this week's realized synthetic values.
                state.disruption_hist.append(seasonal_disruption_days)
                state.zdi_mean_hist.append(zdi_mean)
                state.zdi_p95_hist.append(zdi_p95)

    diagnostics = {"years": len(years), "zones": len(zones), "rows": len(rows)}
    return rows, diagnostics


def write_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "zone_id",
        "year",
        "week_of_year",
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
        "seasonal_disruption_days",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_metadata(
    output_path: Path,
    seed: int,
    years: list[int],
    zone_count: int,
    row_count: int,
    active_only_requested: bool,
    active_filter_applied: bool,
) -> Path:
    metadata = {
        "dataset_name": "ds_disruption_frequency_zone_week",
        "seed": seed,
        "years_simulated": len(years),
        "start_year": years[0],
        "end_year": years[-1],
        "zone_count": zone_count,
        "row_count": row_count,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "active_only_requested": active_only_requested,
        "active_filter_applied": active_filter_applied,
        "csv_file": str(output_path),
    }
    metadata_path = output_path.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata_path


def main() -> int:
    args = parse_args()
    if args.years <= 0:
        raise SystemExit("--years must be > 0")

    now_year = datetime.now(timezone.utc).year
    start_year = args.start_year if args.start_year is not None else (now_year - args.years + 1)
    years = [start_year + i for i in range(args.years)]

    script_path = Path(__file__).resolve()
    repo_root = resolve_repo_root(script_path.parent) or script_path.parents[1]
    rng = random.Random(args.seed)
    SessionLocal, Zone = init_backend(repo_root)

    db = SessionLocal()
    try:
        zone_columns = set(Zone.__table__.columns.keys())
        query = db.query(Zone)
        active_filter_applied = False
        if args.active_only and "is_active" in zone_columns:
            query = query.filter(Zone.is_active == True)
            active_filter_applied = True

        zones = query.order_by(Zone.zone_id.asc()).all()
        if not zones:
            raise SystemExit("No zones found in database.")

        rows, diag = build_rows(zones=zones, years=years, rng=rng)

        output_path = Path(args.output).resolve() if args.output else resolve_default_output_path(script_path.parent)
        write_csv(rows, output_path)
        metadata_path = write_metadata(
            output_path=output_path,
            seed=args.seed,
            years=years,
            zone_count=diag["zones"],
            row_count=diag["rows"],
            active_only_requested=args.active_only,
            active_filter_applied=active_filter_applied,
        )

        print("Dataset generation complete.")
        print(f"zones_used={diag['zones']} years={diag['years']} rows={diag['rows']}")
        print(f"csv={output_path}")
        print(f"metadata={metadata_path}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
