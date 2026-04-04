import random
from datetime import datetime

from app.adapters.mock_state import clamp, load_state, maybe_shift_trend, save_state
from app.interfaces.signal_provider import SignalProvider, SignalReading


# Bengaluru zone rain profiles.
ZONE_RAIN_PROFILES = {
    "BLR-01": {"base": 4.0, "variance": 18.0},
    "BLR-02": {"base": 3.0, "variance": 14.0},
    "BLR-03": {"base": 5.0, "variance": 20.0},
    "BLR-04": {"base": 2.5, "variance": 12.0},
    "BLR-05": {"base": 1.5, "variance": 8.0},
    "BLR-06": {"base": 3.0, "variance": 15.0},
}
DEFAULT_PROFILE = {"base": 2.0, "variance": 10.0}


class MockWeatherAdapter(SignalProvider):
    """
    Stateful rainfall mock:
    - gradual drift around zone baseline
    - occasional storm mode with sharper increases
    - no unrealistic jumps outside event mode
    """

    SOURCE_ID = "mock_weather_v2"

    def get_signal_type(self) -> str:
        return "RAINFALL"

    def fetch(self, zone_id: str) -> SignalReading:
        try:
            profile = ZONE_RAIN_PROFILES.get(zone_id, DEFAULT_PROFILE)
            base = float(profile["base"])
            variance = float(profile["variance"])

            default_state = {
                "last_value": base,
                "trend": random.choice([-1, 0, 1]),
                "event_mode": None,
                "event_steps_left": 0,
            }
            state = load_state(self.get_signal_type(), zone_id, default_state)

            last_value = float(state.get("last_value", base))
            trend = int(state.get("trend", 0))
            event_mode = state.get("event_mode")
            event_steps_left = int(state.get("event_steps_left", 0))

            # Low probability storm start. Storm allows sharper moves.
            if event_mode is None and random.random() < 0.015:
                event_mode = "storm"
                event_steps_left = random.randint(2, 8)
                trend = 1

            if event_mode == "storm":
                event_steps_left = max(0, event_steps_left - 1)
                drift = random.uniform(2.5, 8.0)
                noise = random.uniform(-1.0, 1.5)
                next_value = last_value + drift + noise
                if event_steps_left == 0:
                    event_mode = None
                    trend = -1
            else:
                trend = maybe_shift_trend(trend, change_probability=0.18)
                mean_reversion = (base - last_value) * 0.22
                drift = trend * random.uniform(0.4, 1.8)
                noise = random.uniform(-0.8, 0.8)
                next_value = last_value + mean_reversion + drift + noise

                # Non-event jumps are limited.
                max_delta = 2.8 + (variance * 0.03)
                lower_bound = last_value - max_delta
                upper_bound = last_value + max_delta
                next_value = clamp(next_value, lower_bound, upper_bound)

            raw = round(clamp(next_value, 0.0, 60.0), 2)

            save_state(
                self.get_signal_type(),
                zone_id,
                {
                    "last_value": raw,
                    "trend": trend,
                    "event_mode": event_mode,
                    "event_steps_left": event_steps_left,
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
        if raw_value < 2.5:
            return 0
        elif raw_value < 7.0:
            return int(1 + (raw_value - 2.5) / 4.5 * 23)
        elif raw_value < 15.0:
            return int(25 + (raw_value - 7.0) / 8.0 * 24)
        elif raw_value < 25.0:
            return int(50 + (raw_value - 15.0) / 10.0 * 24)
        else:
            return min(100, int(75 + (raw_value - 25.0) / 10.0 * 25))

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
