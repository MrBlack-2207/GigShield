from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class WalletBalanceOut(BaseModel):
    wallet_id: Optional[str]
    worker_id: str
    balance: float
    updated_at: Optional[datetime]


class WalletTransactionOut(BaseModel):
    id: str
    wallet_id: str
    amount: float
    type: str
    reference_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CashOutRequest(BaseModel):
    worker_id: str


class CashOutResponse(BaseModel):
    withdrawal_id: str
    withdrawn_amount: float
    remaining_wallet_balance: float


class WithdrawalRequestOut(BaseModel):
    id: str
    wallet_id: str
    worker_id: str
    amount: float
    status: str
    reference_id: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
