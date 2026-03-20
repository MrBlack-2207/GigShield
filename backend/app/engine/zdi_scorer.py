# gigshield/backend/app/engine/zdi_scorer.py

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from app.interfaces.signal_provider import SignalReading

# ── ZDI weights (locked from design doc) ─────────────────────────────────────
ZDI_WEIGHTS: dict[str, float] = {
    "RAINFALL":        0.45,
    "PLATFORM_OUTAGE": 0.30,
    "TRAFFIC":         0.15,
    "AQI":             0.10,
}

# ── Payout ladder (locked from design doc) ───────────────────────────────────
# (min_zdi_inclusive, level, payout_pct)
ZDI_LADDER: list[tuple[int, str, int]] = [
    (85, "EXTREME",  100),
    (65, "SEVERE",    75),
    (45, "MODERATE",  50),
    (25, "MILD",      25),
    (0,  "NONE",       0),
]


@dataclass
class ZDIResult:
    """
    Output of one ZDI computation cycle for a single zone.
    Persisted to zdi_snapshots table.
    """
    zone_id:           str
    zdi_score:         int        # 0–100
    disruption_level:  str        # NONE|MILD|MODERATE|SEVERE|EXTREME
    payout_pct:        int        # 0|25|50|75|100
    rain_component:    int
    outage_component:  int
    traffic_component: int
    aqi_component:     int
    snapshot_at:       datetime
    is_disruption:     bool       # True when ZDI >= 25


def compute_zdi(zone_id: str, readings: list[SignalReading]) -> ZDIResult:
    """
    Computes the Zone Disruption Index for one zone from a list of
    SignalReading objects — one per signal type.

    Missing signal types default to 0 (safe degradation — one broken
    adapter never inflates the score).
    """
    score_map: dict[str, int] = {r.signal_type: r.normalized_score for r in readings}

    rain_component    = score_map.get("RAINFALL",        0)
    outage_component  = score_map.get("PLATFORM_OUTAGE", 0)
    traffic_component = score_map.get("TRAFFIC",         0)
    aqi_component     = score_map.get("AQI",             0)

    raw_zdi = (
        rain_component    * ZDI_WEIGHTS["RAINFALL"]        +
        outage_component  * ZDI_WEIGHTS["PLATFORM_OUTAGE"] +
        traffic_component * ZDI_WEIGHTS["TRAFFIC"]         +
        aqi_component     * ZDI_WEIGHTS["AQI"]
    )

    zdi_score = int(min(max(round(raw_zdi), 0), 100))
    level, payout_pct = _classify(zdi_score)

    return ZDIResult(
        zone_id=zone_id,
        zdi_score=zdi_score,
        disruption_level=level,
        payout_pct=payout_pct,
        rain_component=rain_component,
        outage_component=outage_component,
        traffic_component=traffic_component,
        aqi_component=aqi_component,
        snapshot_at=datetime.utcnow(),
        is_disruption=(zdi_score >= 25),
    )


def _classify(zdi: int) -> tuple[str, int]:
    for threshold, level, pct in ZDI_LADDER:
        if zdi >= threshold:
            return level, pct
    return "NONE", 0