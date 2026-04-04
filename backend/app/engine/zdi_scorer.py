from dataclasses import dataclass, field
from datetime import datetime

from app.interfaces.signal_provider import SignalReading

# ZDI weights (locked from design doc)
ZDI_WEIGHTS: dict[str, float] = {
    "RAINFALL": 0.45,
    "PLATFORM_OUTAGE": 0.30,
    "TRAFFIC": 0.15,
    "AQI": 0.10,
}

# Event signal boosts added on top of base ZDI.
# Core weighted formula remains unchanged.
EVENT_ZDI_BOOSTS: dict[str, int] = {
    "strike": 15,
    "petrol_crisis": 20,
    "bandh": 30,
    "curfew": 40,
    "lockdown": 50,
}

# Payout ladder (locked from design doc)
# (min_zdi_inclusive, level, payout_pct)
ZDI_LADDER: list[tuple[int, str, int]] = [
    (85, "EXTREME", 100),
    (65, "SEVERE", 75),
    (45, "MODERATE", 50),
    (25, "MILD", 25),
    (0, "NONE", 0),
]


@dataclass
class ZDIResult:
    """
    Output of one ZDI computation cycle for a single zone.
    Persisted to zdi_snapshots table.
    """

    zone_id: str
    zdi_score: int  # 0-100
    disruption_level: str  # NONE|MILD|MODERATE|SEVERE|EXTREME
    payout_pct: int  # 0|25|50|75|100
    rain_component: int
    outage_component: int
    traffic_component: int
    aqi_component: int
    snapshot_at: datetime
    is_disruption: bool  # True when ZDI >= 25
    base_zdi: int = 0
    event_boost_total: int = 0
    final_zdi: int = 0
    active_event_signals: list[str] = field(default_factory=list)


def compute_zdi(zone_id: str, readings: list[SignalReading]) -> ZDIResult:
    """
    Computes the Zone Disruption Index for one zone from a list of
    SignalReading objects for the same interval.

    - Core signals (rain/outage/traffic/aqi) produce base_zdi.
    - Event signals add deterministic boosts.
    - Missing signals default to 0.
    """
    score_map: dict[str, int] = {r.signal_type: r.normalized_score for r in readings}

    rain_component = score_map.get("RAINFALL", 0)
    outage_component = score_map.get("PLATFORM_OUTAGE", 0)
    traffic_component = score_map.get("TRAFFIC", 0)
    aqi_component = score_map.get("AQI", 0)

    raw_zdi = (
        rain_component * ZDI_WEIGHTS["RAINFALL"]
        + outage_component * ZDI_WEIGHTS["PLATFORM_OUTAGE"]
        + traffic_component * ZDI_WEIGHTS["TRAFFIC"]
        + aqi_component * ZDI_WEIGHTS["AQI"]
    )

    base_zdi = int(min(max(round(raw_zdi), 0), 100))
    event_boost_total, active_event_signals = _compute_event_boost(readings)
    final_zdi = min(100, base_zdi + event_boost_total)

    level, payout_pct = _classify(final_zdi)

    return ZDIResult(
        zone_id=zone_id,
        zdi_score=final_zdi,
        disruption_level=level,
        payout_pct=payout_pct,
        rain_component=rain_component,
        outage_component=outage_component,
        traffic_component=traffic_component,
        aqi_component=aqi_component,
        snapshot_at=datetime.utcnow(),
        is_disruption=(final_zdi >= 25),
        base_zdi=base_zdi,
        event_boost_total=event_boost_total,
        final_zdi=final_zdi,
        active_event_signals=active_event_signals,
    )


def _classify(zdi: int) -> tuple[str, int]:
    for threshold, level, pct in ZDI_LADDER:
        if zdi >= threshold:
            return level, pct
    return "NONE", 0


def _compute_event_boost(readings: list[SignalReading]) -> tuple[int, list[str]]:
    """
    Computes cumulative boost from active event flags in the same interval.
    Multiple events are additive, then final ZDI is capped by caller.
    """
    total = 0
    active: list[str] = []

    for reading in readings:
        signal_key = str(reading.signal_type).lower()
        boost = EVENT_ZDI_BOOSTS.get(signal_key)
        if boost is None:
            continue

        is_active = float(reading.raw_value) >= 1.0 or int(reading.normalized_score) >= 100
        if is_active:
            total += boost
            active.append(signal_key)

    return total, active
