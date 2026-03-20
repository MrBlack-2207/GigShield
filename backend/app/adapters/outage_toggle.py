# gigshield/backend/app/adapters/outage_toggle.py

from datetime import datetime
import redis as redis_lib
from app.interfaces.signal_provider import SignalProvider, SignalReading
from app.config import get_settings

settings = get_settings()

# Redis key pattern: "outage:{zone_id}"
# Admin sets this via POST /api/admin/outage/toggle
# Production replacement: StatusPageWebhookAdapter or ZeptoHealthCheckAdapter
# — same SignalProvider interface, different fetch() implementation


class OutageToggleAdapter(SignalProvider):
    """
    Reads admin-controlled outage flags from Redis.

    Admin sets  → redis.set("outage:BLR-01", "1")  → outage active
    Admin clears→ redis.delete("outage:BLR-01")     → normal

    Raw value:        1.0 (outage) | 0.0 (normal)
    Normalized score: 100 (outage) | 0   (normal)

    Production swap:
        Create adapters/statuspage_adapter.py
        Inherit SignalProvider, implement fetch() to call StatusPage API
        Update adapter_factory.py — nothing else changes.
    """

    SOURCE_ID = "admin_toggle_v1"

    def __init__(self):
        self._redis = redis_lib.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )

    def get_signal_type(self) -> str:
        return "PLATFORM_OUTAGE"

    def fetch(self, zone_id: str) -> SignalReading:
        try:
            flag = self._redis.get(f"outage:{zone_id}")
            is_down = flag == "1"
            raw_value = 1.0 if is_down else 0.0

            return SignalReading(
                zone_id=zone_id,
                signal_type=self.get_signal_type(),
                raw_value=raw_value,
                normalized_score=self.normalize(raw_value),
                source_id=self.SOURCE_ID,
                is_mocked=True,
                recorded_at=datetime.utcnow(),
            )
        except Exception:
            # Redis unavailable — treat as no outage, do not crash scheduler
            return self._zero_reading(zone_id)

    def normalize(self, raw_value: float) -> int:
        return 100 if raw_value == 1.0 else 0

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