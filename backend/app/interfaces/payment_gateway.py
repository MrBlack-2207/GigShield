# gigshield/backend/app/interfaces/payment_gateway.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PaymentResult:
    """
    Returned by every payment gateway adapter after a disbursement attempt.
    """
    success:     bool
    gateway_ref: str        # "MOCK_TXN_XXXXX" | Razorpay payout ID
    is_mocked:   bool
    amount_inr:  float
    method:      str        # UPI_MOCK | UPI | BANK_TRANSFER
    initiated_at: datetime
    error_message: str = "" # populated only on failure


class PaymentGateway(ABC):
    """
    Abstract base for all payment adapters.
    MockPaymentGateway is used in demo.
    RazorpayGateway would be production — same interface, different file.
    """

    @abstractmethod
    def disburse(
        self,
        worker_id:   str,
        claim_id:    str,
        amount_inr:  float,
        reference:   str,
    ) -> PaymentResult:
        """
        Initiate a payout to the worker.
        Returns a PaymentResult regardless of success or failure.
        Must never raise — wrap exceptions and return result with success=False.
        """
        ...