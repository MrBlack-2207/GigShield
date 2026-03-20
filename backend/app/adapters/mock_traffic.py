# gigshield/backend/app/adapters/mock_traffic.py

import random
from datetime import datetime
from app.interfaces.signal_provider import SignalProvider, SignalReading


# Bengaluru traffic congestion profiles
# raw_value = speed reduction % (0 = free flow, 100 = standstill)
ZONE_TRAFFIC_PROFILES = {
    "BLR-01": {"base": 25.0, "variance": 20.0},  # Koramangala — high traffic
    "BLR-02": {"base": 30.0, "variance": 20.0},  # Indiranagar — high
    "BLR-03": {"base": 20.0, "variance": 15.0},  # HSR Layout — medium
    "BLR-04": {"base": 25.0, "variance": 18.0},  # Whitefield — IT corridor
    "BLR-05": {"base": 15.0, "variance": 12.0},  # Jayanagar — low
    "BLR-06": {"base": 28.0, "variance": 20.0},  # Hebbal — flyover congestion
}
DEFAULT_PROFILE = {"base": 20.0, "variance": 15.0}


class MockTrafficAdapter(SignalProvider):
    """
    Generates synthetic traffic congestion data.

    Raw value: speed reduction percentage (0–100)
    Normalization thresholds (locked from design doc):
        < 20%  reduction → 0     (free flow)
        20–40% reduction → 1–24
        40–60% reduction → 25–74
        > 60%  reduction → 75–100 (severe congestion)
    """

    SOURCE_ID = "mock_traffic_v1"

    def get_signal_type(self) -> str:
        return "TRAFFIC"

    def fetch(self, zone_id: str) -> SignalReading:
        try:
            profile = ZONE_TRAFFIC_PROFILES.get(zone_id, DEFAULT_PROFILE)
            raw = max(0.0, min(100.0, random.gauss(profile["base"], profile["variance"] / 3)))
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