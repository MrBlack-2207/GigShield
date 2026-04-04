from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.worker import Worker
from app.schemas.wallet import (
    CashOutRequest,
    CashOutResponse,
    WalletBalanceOut,
    WalletTransactionOut,
    WithdrawalRequestOut,
)
from app.services.wallet_service import (
    cash_out_wallet,
    get_wallet_for_worker,
    list_wallet_transactions,
    list_withdrawal_requests,
)

router = APIRouter()


@router.get("/balance", response_model=WalletBalanceOut)
def get_wallet_balance(
    worker_id: str = Query(...),
    db: Session = Depends(get_db),
):
    worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    wallet = get_wallet_for_worker(db, worker_id)
    if not wallet:
        return WalletBalanceOut(
            wallet_id=None,
            worker_id=worker_id,
            balance=0.0,
            updated_at=None,
        )

    return WalletBalanceOut(
        wallet_id=wallet.id,
        worker_id=worker_id,
        balance=float(wallet.balance),
        updated_at=wallet.updated_at,
    )


@router.get("/transactions", response_model=list[WalletTransactionOut])
def get_wallet_transactions(
    worker_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    return list_wallet_transactions(
        db=db,
        worker_id=worker_id,
        limit=limit,
        offset=offset,
    )


@router.post("/cashout", response_model=CashOutResponse)
def cashout_wallet(
    body: CashOutRequest,
    db: Session = Depends(get_db),
):
    worker = db.query(Worker).filter(Worker.worker_id == body.worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    try:
        withdrawal, withdrawn_amount, remaining_balance = cash_out_wallet(
            db=db,
            worker_id=body.worker_id,
        )
        return CashOutResponse(
            withdrawal_id=withdrawal.id,
            withdrawn_amount=float(withdrawn_amount),
            remaining_wallet_balance=float(remaining_balance),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/withdrawals", response_model=list[WithdrawalRequestOut])
def get_withdrawals(
    worker_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    return list_withdrawal_requests(
        db=db,
        worker_id=worker_id,
        limit=limit,
        offset=offset,
    )
