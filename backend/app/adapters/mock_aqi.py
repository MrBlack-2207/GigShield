# gigshield/backend/app/adapters/mock_aqi.py

import random
from datetime import datetime
from app.interfaces.signal_provider import SignalProvider, SignalReading


# Bengaluru AQI is generally better than Delhi
# but spikes during Diwali, crop burning season, construction
ZONE_AQI_PROFILES = {
    "BLR-01": {"base": 95.0,  "variance": 40.0},
    "BLR-02": {"base": 90.0,  "variance": 35.0},
    "BLR-03": {"base": 100.0, "variance": 45.0},
    "BLR-04": {"base": 110.0, "variance": 50.0},  # Whitefield — industrial
    "BLR-05": {"base": 80.0,  "variance": 30.0},  # Jayanagar — greener
    "BLR-06": {"base": 105.0, "variance": 45.0},
}
DEFAULT_PROFILE = {"base": 95.0, "variance": 40.0}


class MockAQIAdapter(SignalProvider):
    """
    Generates synthetic Air Quality Index data.

    Raw value: AQI index (CPCB India scale: 0–500)
    Normalization thresholds (locked from design doc):
        < 150  AQI → 0      (good/satisfactory)
        150–200 AQI → 1–24
        200–300 AQI → 25–74 (poor — delivery disruption likely)
        > 300  AQI → 75–100 (very poor / severe)
    """

    SOURCE_ID = "mock_aqi_v1"

    def get_signal_type(self) -> str:
        return "AQI"

    def fetch(self, zone_id: str) -> SignalReading:
        try:
            profile = ZONE_AQI_PROFILES.get(zone_id, DEFAULT_PROFILE)
            raw = max(0.0, random.gauss(profile["base"], profile["variance"] / 3))
            raw = round(raw, 1)

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
        if raw_value < 150.0:
            return 0
        elif raw_value < 200.0:
            return int(1 + (raw_value - 150.0) / 50.0 * 23)
        elif raw_value < 300.0:
            return int(25 + (raw_value - 200.0) / 100.0 * 49)
        else:
            return min(100, int(75 + (raw_value - 300.0) / 200.0 * 25))

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