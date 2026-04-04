import random
from datetime import datetime
from zoneinfo import ZoneInfo

from app.adapters.mock_state import clamp, load_state, maybe_shift_trend, save_state
from app.interfaces.signal_provider import SignalProvider, SignalReading


# Bengaluru traffic congestion profiles.
# raw_value = speed reduction % (0 = free flow, 100 = standstill)
ZONE_TRAFFIC_PROFILES = {
    "BLR-01": {"base": 25.0, "variance": 20.0},
    "BLR-02": {"base": 30.0, "variance": 20.0},
    "BLR-03": {"base": 20.0, "variance": 15.0},
    "BLR-04": {"base": 25.0, "variance": 18.0},
    "BLR-05": {"base": 15.0, "variance": 12.0},
    "BLR-06": {"base": 28.0, "variance": 20.0},
}
DEFAULT_PROFILE = {"base": 20.0, "variance": 15.0}

_IST = ZoneInfo("Asia/Kolkata")


def _peak_hour_uplift() -> float:
    hour = datetime.now(_IST).hour
    if 8 <= hour <= 11:
        return 12.0
    if 17 <= hour <= 21:
        return 15.0
    if 12 <= hour <= 15:
        return 5.0
    return 0.0


class MockTrafficAdapter(SignalProvider):
    """
    Stateful traffic mock:
    - smooth correlation across 15-min ticks
    - peak hour uplift in IST
    - bounded non-event changes
    """

    SOURCE_ID = "mock_traffic_v2"

    def get_signal_type(self) -> str:
        return "TRAFFIC"

    def fetch(self, zone_id: str) -> SignalReading:
        try:
            profile = ZONE_TRAFFIC_PROFILES.get(zone_id, DEFAULT_PROFILE)
            base = float(profile["base"]) + _peak_hour_uplift()

            default_state = {
                "last_value": base,
                "trend": random.choice([-1, 0, 1]),
                "event_mode": None,
            }
            state = load_state(self.get_signal_type(), zone_id, default_state)

            last_value = float(state.get("last_value", base))
            trend = int(state.get("trend", 0))
            trend = maybe_shift_trend(trend, change_probability=0.16)

            mean_reversion = (base - last_value) * 0.25
            drift = trend * random.uniform(0.8, 2.8)
            noise = random.uniform(-1.4, 1.4)
            next_value = last_value + mean_reversion + drift + noise

            # Smooth bounded moves between consecutive ticks.
            max_delta = 5.5
            next_value = clamp(next_value, last_value - max_delta, last_value + max_delta)
            raw = round(clamp(next_value, 0.0, 100.0), 2)

            save_state(
                self.get_signal_type(),
                zone_id,
                {
                    "last_value": raw,
                    "trend": trend,
                    "event_mode": None,
                },
            )

            return SignalReading(
                zone_id=zone_id,
                signal_type=self.get_signal_type(),
                raw_value=raw,
                normalized_score=self.normalize(raw),
                source_id=self.SOURCE_ID,
                is_mocked=True,
                recorded_at=datetime.utcnow(),
            )
        except Exception:
            return self._zero_reading(zone_id)

    def normalize(self, raw_value: float) -> int:
        if raw_value < 20.0:
            return 0
        elif raw_value < 40.0:
            return int(1 + (raw_value - 20.0) / 20.0 * 23)
        elif raw_value < 60.0:
            return int(25 + (raw_value - 40.0) / 20.0 * 49)
        else:
            return min(100, int(75 + (raw_value - 60.0) / 40.0 * 25))

    def _zero_reading(self, zone_id: str) -> SignalReading:
        return SignalReading(
            zone_id=zone_id,
            signal_type=self.get_signal_type(),
            raw_value=0.0,
            normalized_score=0,
            source_id=self.SOURCE_ID,
            is_mocked=True,
            recorded_at=datetime.utcnow(),
        )
