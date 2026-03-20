# gigshield/backend/app/interfaces/__init__.py

from app.interfaces.signal_provider import SignalProvider, SignalReading
from app.interfaces.payment_gateway import PaymentGateway, PaymentResult

__all__ = [
    "SignalProvider",
    "SignalReading",
    "PaymentGateway",
    "PaymentResult",
]