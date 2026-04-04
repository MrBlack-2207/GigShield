import random
from dataclasses import dataclass
from datetime import datetime

from app.adapters.mock_state import load_state, save_state
from app.config import get_settings
from app.interfaces.signal_provider import SignalProvider, SignalReading

settings = get_settings()

_FULL_DAY_STEPS = 96  # 24 hours x 4 intervals per hour.


@dataclass(frozen=True)
class EventRule:
    signal_type: str
    trigger_probability: float
    min_steps: int
    max_steps: int
    full_day_probability: float
    severity_weight: float


EVENT_RULES: tuple[EventRule, ...] = (
    EventRule(
        signal_type="strike",
        trigger_probability=0.0015,
        min_steps=4,
        max_steps=32,
        full_day_probability=0.03,
        severity_weight=settings.EVENT_WEIGHT_STRIKE,
    ),
    EventRule(
        signal_type="bandh",
        trigger_probability=0.0010,
        min_steps=4,
        max_steps=32,
        full_day_probability=0.05,
        severity_weight=settings.EVENT_WEIGHT_BANDH,
    ),
    EventRule(
        signal_type="petrol_crisis",
        trigger_probability=0.0013,
        min_steps=4,
        max_steps=28,
        full_day_probability=0.02,
        severity_weight=settings.EVENT_WEIGHT_PETROL_CRISIS,
    ),
    EventRule(
        signal_type="lockdown",
        trigger_probability=0.0004,
        min_steps=8,
        max_steps=32,
        full_day_probability=0.20,
        severity_weight=settings.EVENT_WEIGHT_LOCKDOWN,
    ),
    EventRule(
        signal_type="curfew",
        trigger_probability=0.0009,
        min_steps=6,
        max_steps=32,
        full_day_probability=0.12,
        severity_weight=settings.EVENT_WEIGHT_CURFEW,
    ),
)


class MockEventFlagAdapter(SignalProvider):
    """
    Generates rare event-window based binary signals.
    Each zone keeps independent state in Redis/in-memory fallback via mock_state.
    """

    SOURCE_ID = "mock_event_flags_v1"

    def __init__(self, rule: EventRule):
        self.rule = rule

    def get_signal_type(self) -> str:
        return self.rule.signal_type

    def fetch(self, zone_id: str) -> SignalReading:
        try:
            state = load_state(
                self.get_signal_type(),
                zone_id,
                {
                    "is_active": False,
                    "remaining_duration": 0,
                    "started_at": None,
                    "total_duration_steps": 0,
                    "severity_weight": self.rule.severity_weight,
                },
            )

            is_active = bool(state.get("is_active", False))
            remaining_duration = int(state.get("remaining_duration", 0))
            started_at = state.get("started_at")
            total_duration_steps = int(state.get("total_duration_steps", 0))

            if is_active and remaining_duration > 0:
                raw_value = 1.0
                remaining_duration -= 1
                if remaining_duration == 0:
                    is_active = False
                    started_at = None
                    total_duration_steps = 0
            else:
                is_active = False
                remaining_duration = 0
                started_at = None
                total_duration_steps = 0

                if random.random() < self.rule.trigger_probability:
                    total_duration_steps = self._pick_duration_steps()
                    remaining_duration = max(0, total_duration_steps - 1)
                    started_at = datetime.utcnow().isoformat()
                    is_active = True
                    raw_value = 1.0
                else:
                    raw_value = 0.0

            save_state(
                self.get_signal_type(),
                zone_id,
                {
                    "is_active": is_active,
                    "remaining_duration": remaining_duration,
                    "started_at": started_at,
                    "total_duration_steps": total_duration_steps,
                    "severity_weight": self.rule.severity_weight,
                },
            )

            return SignalReading(
                zone_id=zone_id,
                signal_type=self.get_signal_type(),
                raw_value=raw_value,
                normalized_score=self.normalize(raw_value),
                source_id=self._source_id(),
                is_mocked=True,
                recorded_at=datetime.utcnow(),
            )
        except Exception:
            return self._zero_reading(zone_id)

    def normalize(self, raw_value: float) -> int:
        return 100 if raw_value >= 1.0 else 0

    def _pick_duration_steps(self) -> int:
        if random.random() < self.rule.full_day_probability:
            return _FULL_DAY_STEPS
        return random.randint(self.rule.min_steps, self.rule.max_steps)

    def _source_id(self) -> str:
        # Store severity weight with each reading in existing schema (source_id).
        return f"{self.SOURCE_ID}|w={self.rule.severity_weight:.2f}"

    def _zero_reading(self, zone_id: str) -> SignalReading:
        return SignalReading(
            zone_id=zone_id,
            signal_type=self.get_signal_type(),
            raw_value=0.0,
            normalized_score=0,
            source_id=self._source_id(),
            is_mocked=True,
            recorded_at=datetime.utcnow(),
        )


def get_event_flag_adapters() -> list[SignalProvider]:
    return [MockEventFlagAdapter(rule) for rule in EVENT_RULES]
