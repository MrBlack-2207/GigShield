# gigshield/backend/app/adapters/mock_weather.py

import random
from datetime import datetime
from app.interfaces.signal_provider import SignalProvider, SignalReading


# Bengaluru zone risk profiles — drives realistic mock data
# Matches the zone risk tiers we defined in our design doc
ZONE_RAIN_PROFILES = {
    "BLR-01": {"base": 4.0,  "variance": 18.0},  # Koramangala — high rain
    "BLR-02": {"base": 3.0,  "variance": 14.0},  # Indiranagar — medium/high
    "BLR-03": {"base": 5.0,  "variance": 20.0},  # HSR Layout — high (low-lying)
    "BLR-04": {"base": 2.5,  "variance": 12.0},  # Whitefield — medium
    "BLR-05": {"base": 1.5,  "variance": 8.0},   # Jayanagar — low
    "BLR-06": {"base": 3.0,  "variance": 15.0},  # Hebbal — medium
}
DEFAULT_PROFILE = {"base": 2.0, "variance": 10.0}


class MockWeatherAdapter(SignalProvider):
    """
    Generates synthetic rainfall data using per-zone risk profiles.

    Raw value: mm/hr (millimetres per hour)
    Normalization thresholds (locked from design doc):
        < 2.5  mm/hr  → 0    (no disruption)
        2.5–7  mm/hr  → 1–24  (approaching mild)
        7–15   mm/hr  → 25–49 (mild to moderate)
        15–25  mm/hr  → 50–74 (moderate to severe)
        > 25   mm/hr  → 75–100 (severe to extreme)
    """

    SOURCE_ID = "mock_weather_v1"

    def get_signal_type(self) -> str:
        return "RAINFALL"

    def fetch(self, zone_id: str) -> SignalReading:
        try:
            profile = ZONE_RAIN_PROFILES.get(zone_id, DEFAULT_PROFILE)
            # Weighted random: most readings are low, spikes are realistic
            raw = max(0.0, random.gauss(profile["base"], profile["variance"] / 4))
            raw = round(raw, 2)

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
            # Never let an adapter crash the scheduler
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