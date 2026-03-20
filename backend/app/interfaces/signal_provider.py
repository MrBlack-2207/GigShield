# gigshield/backend/app/interfaces/signal_provider.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SignalReading:
    """
    The single output shape every signal adapter must return.
    Downstream engine code only ever sees this — never the adapter itself.
    """
    zone_id:          str
    signal_type:      str       # RAINFALL | PLATFORM_OUTAGE | TRAFFIC | AQI
    raw_value:        float     # mm/hr | 0or1 | speed_reduction_pct | AQI_index
    normalized_score: int       # 0–100, computed by the adapter
    source_id:        str       # "mock_weather_v1" | "openweathermap_v3" etc.
    is_mocked:        bool
    recorded_at:      datetime


class SignalProvider(ABC):
    """
    Abstract base class every signal adapter must implement.
    The ZDI engine depends only on this interface — never on a concrete adapter.

    To add a real API in production:
        1. Create backend/app/adapters/openweathermap.py
        2. Inherit from SignalProvider
        3. Implement all three methods below
        4. Update adapter_factory.py to return it when USE_MOCK_WEATHER=false
        Done. Nothing else in the codebase changes.
    """

    @abstractmethod
    def get_signal_type(self) -> str:
        """Return one of: RAINFALL | PLATFORM_OUTAGE | TRAFFIC | AQI"""
        ...

    @abstractmethod
    def fetch(self, zone_id: str) -> SignalReading:
        """
        Fetch the current signal value for a zone and return a SignalReading.
        Must never raise — return a zero-value reading on failure.
        """
        ...

    @abstractmethod
    def normalize(self, raw_value: float) -> int:
        """
        Convert raw measurement to a 0–100 score.
        Thresholds are locked from our design doc:

        RAINFALL:        <2.5 → 0   | 7–15 → ~50  | >25 → 100
        PLATFORM_OUTAGE: 0 → 0      | 1 → 100
        TRAFFIC:         <20% drop → 0 | 40–60% → 50 | >60% → 100
        AQI:             <150 → 0   | 200–300 → 50 | >300 → 100
        """
        ...