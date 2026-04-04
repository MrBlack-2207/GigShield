# gigshield/backend/app/adapters/__init__.py

from app.adapters.adapter_factory import (
    get_weather_adapter,
    get_traffic_adapter,
    get_aqi_adapter,
    get_outage_adapter,
    get_event_flag_adapters,
    get_payment_gateway,
)

__all__ = [
    "get_weather_adapter",
    "get_traffic_adapter",
    "get_aqi_adapter",
    "get_outage_adapter",
    "get_event_flag_adapters",
    "get_payment_gateway",
]
