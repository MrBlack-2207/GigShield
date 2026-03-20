# gigshield/backend/app/adapters/mock_payment.py

import uuid
from datetime import datetime
from app.interfaces.payment_gateway import PaymentGateway, PaymentResult


class MockPaymentGateway(PaymentGateway):
    """
    Simulates instant UPI payouts for demo.
    Always succeeds unless amount is zero or negative.

    Production swap:
        Create adapters/razorpay_gateway.py
        Inherit PaymentGateway, implement disburse() with Razorpay SDK
        Update adapter_factory.py — nothing else changes.
    """

    def disburse(
        self,
        worker_id:  str,
        claim_id:   str,
        amount_inr: float,
        reference:  str,
    ) -> PaymentResult:
        try:
            if amount_inr <= 0:
                return PaymentResult(
                    success=False,
                    gateway_ref="",
                    is_mocked=True,
                    amount_inr=amount_inr,
                    method="UPI_MOCK",
                    initiated_at=datetime.utcnow(),
                    error_message="Amount must be greater than zero.",
                )

            mock_ref = f"MOCK_TXN_{uuid.uuid4().hex[:10].upper()}"

            return PaymentResult(
                success=True,
                gateway_ref=mock_ref,
                is_mocked=True,
                amount_inr=amount_inr,
                method="UPI_MOCK",
                initiated_at=datetime.utcnow(),
            )

        except Exception as e:
            return PaymentResult(
                success=False,
                gateway_ref="",
                is_mocked=True,
                amount_inr=amount_inr,
                method="UPI_MOCK",
                initiated_at=datetime.utcnow(),
                error_message=str(e),
            )