# gigshield/backend/app/adapters/adapter_factory.py

from app.config import get_settings
from app.interfaces.signal_provider import SignalProvider
from app.interfaces.payment_gateway import PaymentGateway

settings = get_settings()


def get_weather_adapter() -> SignalProvider:
    if settings.USE_MOCK_WEATHER:
        from app.adapters.mock_weather import MockWeatherAdapter
        return MockWeatherAdapter()
    # Production:
    # from app.adapters.openweathermap import OpenWeatherMapAdapter
    # return OpenWeatherMapAdapter()
    raise NotImplementedError("Real weather adapter not configured.")


def get_traffic_adapter() -> SignalProvider:
    if settings.USE_MOCK_TRAFFIC:
        from app.adapters.mock_traffic import MockTrafficAdapter
        return MockTrafficAdapter()
    # Production:
    # from app.adapters.tomtom import TomTomTrafficAdapter
    # return TomTomTrafficAdapter()
    raise NotImplementedError("Real traffic adapter not configured.")


def get_aqi_adapter() -> SignalProvider:
    if settings.USE_MOCK_AQI:
        from app.adapters.mock_aqi import MockAQIAdapter
        return MockAQIAdapter()
    # Production:
    # from app.adapters.cpcb import CPCBAQIAdapter
    # return CPCBAQIAdapter()
    raise NotImplementedError("Real AQI adapter not configured.")


def get_outage_adapter() -> SignalProvider:
    # Outage toggle always uses Redis flag in both demo and production
    # Production: swap OutageToggleAdapter for StatusPageWebhookAdapter
    from app.adapters.outage_toggle import OutageToggleAdapter
    return OutageToggleAdapter()


def get_payment_gateway() -> PaymentGateway:
    if settings.USE_MOCK_PAYMENT:
        from app.adapters.mock_payment import MockPaymentGateway
        return MockPaymentGateway()
    # Production:
    # from app.adapters.razorpay_gateway import RazorpayGateway
    # return RazorpayGateway()
    raise NotImplementedError("Real payment gateway not configured.")