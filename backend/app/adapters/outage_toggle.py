import random
from datetime import datetime

import redis as redis_lib

from app.adapters.mock_state import load_state, save_state
from app.config import get_settings
from app.interfaces.signal_provider import SignalProvider, SignalReading

settings = get_settings()


class OutageToggleAdapter(SignalProvider):
    """
    Reads admin-controlled outage flags from Redis, with a fallback mock outage
    window generator when no manual flag is active.

    Raw value:        1.0 (outage) | 0.0 (normal)
    Normalized score: 100 (outage) | 0   (normal)
    """

    SOURCE_ID = "outage_toggle_v2"

    def __init__(self):
        self._redis = redis_lib.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )

    def get_signal_type(self) -> str:
        return "PLATFORM_OUTAGE"

    def fetch(self, zone_id: str) -> SignalReading:
        try:
            manual_flag = self._get_manual_flag(zone_id)
            if manual_flag is not None:
                raw_value = 1.0 if manual_flag else 0.0
                return SignalReading(
                    zone_id=zone_id,
                    signal_type=self.get_signal_type(),
                    raw_value=raw_value,
                    normalized_score=self.normalize(raw_value),
                    source_id=self.SOURCE_ID,
                    is_mocked=True,
                    recorded_at=datetime.utcnow(),
                )

            default_state = {
                "last_value": 0.0,
                "trend": 0,
                "event_mode": None,
                "event_steps_left": 0,
            }
            state = load_state(self.get_signal_type(), zone_id, default_state)

            event_mode = state.get("event_mode")
            event_steps_left = int(state.get("event_steps_left", 0))

            if event_mode == "outage":
                event_steps_left = max(0, event_steps_left - 1)
                raw_value = 1.0
                if event_steps_left == 0:
                    event_mode = None
            else:
                # Mostly healthy, occasionally enter an outage window.
                if random.random() < 0.005:
                    event_mode = "outage"
                    event_steps_left = random.randint(2, 8)
                    raw_value = 1.0
                else:
                    raw_value = 0.0

            save_state(
                self.get_signal_type(),
                zone_id,
                {
                    "last_value": raw_value,
                    "trend": 0,
                    "event_mode": event_mode,
                    "event_steps_left": event_steps_left,
                },
            )

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
            return self._zero_reading(zone_id)

    def _get_manual_flag(self, zone_id: str) -> bool | None:
        try:
            flag = self._redis.get(f"outage:{zone_id}")
            if flag is None:
                return None
            return flag == "1"
        except Exception:
            # Redis unavailable for manual toggle lookup; use simulated mode.
            return None

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
