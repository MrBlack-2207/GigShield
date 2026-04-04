from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.wallet import Wallet
from app.models.wallet_ledger_entry import WalletLedgerEntry
from app.models.withdrawal_request import WithdrawalRequest

ENTRY_TYPES = {"payout", "withdrawal", "premium", "adjustment"}
REFERENCE_REQUIRED_TYPES = {"payout", "premium", "withdrawal"}


def get_wallet_for_worker(db: Session, worker_id: str) -> Wallet | None:
    return db.query(Wallet).filter(Wallet.worker_id == worker_id).first()


def get_or_create_wallet(db: Session, worker_id: str) -> Wallet:
    wallet = get_wallet_for_worker(db, worker_id)
    if wallet:
        return wallet

    wallet = Wallet(worker_id=worker_id, balance=Decimal("0.00"))
    db.add(wallet)
    db.flush()
    return wallet


def apply_wallet_entry(
    db: Session,
    worker_id: str,
    amount: Decimal | float | int | str,
    entry_type: str,
    reference_id: str | None = None,
) -> tuple[Wallet, WalletLedgerEntry, bool]:
    """
    Applies one wallet entry atomically:
    1) insert ledger row
    2) increment wallet.balance

    Returns (wallet, ledger_entry, created_new_entry).
    """
    if entry_type not in ENTRY_TYPES:
        raise ValueError(f"Unsupported wallet entry type: {entry_type}")

    if entry_type in REFERENCE_REQUIRED_TYPES and not reference_id:
        raise ValueError(f"reference_id is required for wallet entry type '{entry_type}'")

    amount_dec = Decimal(str(amount)).quantize(Decimal("0.01"))
    if amount_dec == Decimal("0.00"):
        raise ValueError("Wallet entry amount cannot be zero.")

    wallet = get_or_create_wallet(db, worker_id)

    existing = (
        db.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.wallet_id == wallet.id,
            WalletLedgerEntry.type == entry_type,
            WalletLedgerEntry.reference_id == reference_id,
        )
        .first()
    )
    if existing:
        return wallet, existing, False

    entry = WalletLedgerEntry(
        wallet_id=wallet.id,
        amount=amount_dec,
        type=entry_type,
        reference_id=reference_id,
    )
    db.add(entry)

    current_balance = Decimal(str(wallet.balance or "0")).quantize(Decimal("0.01"))
    wallet.balance = (current_balance + amount_dec).quantize(Decimal("0.01"))

    db.flush()
    return wallet, entry, True


def list_wallet_transactions(
    db: Session,
    worker_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[WalletLedgerEntry]:
    wallet = get_wallet_for_worker(db, worker_id)
    if not wallet:
        return []

    return (
        db.query(WalletLedgerEntry)
        .filter(WalletLedgerEntry.wallet_id == wallet.id)
        .order_by(WalletLedgerEntry.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def cash_out_wallet(
    db: Session,
    worker_id: str,
) -> tuple[WithdrawalRequest, Decimal, Decimal]:
    """
    Withdraws the full wallet balance in one transaction.
    Creates:
    - withdrawal request
    - matching negative wallet ledger entry
    - wallet balance update to 0
    """
    try:
        wallet = (
            db.query(Wallet)
            .filter(Wallet.worker_id == worker_id)
            .with_for_update()
            .first()
        )
        if not wallet:
            raise ValueError("Wallet balance is zero. Cash-out not allowed.")

        current_balance = Decimal(str(wallet.balance or "0")).quantize(Decimal("0.01"))
        if current_balance <= Decimal("0.00"):
            raise ValueError("Wallet balance is zero. Cash-out not allowed.")

        withdrawal = WithdrawalRequest(
            wallet_id=wallet.id,
            worker_id=worker_id,
            amount=current_balance,
            status="requested",
        )
        db.add(withdrawal)
        db.flush()

        db.add(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                amount=(-current_balance).quantize(Decimal("0.01")),
                type="withdrawal",
                reference_id=withdrawal.id,
            )
        )

        wallet.balance = Decimal("0.00")
        withdrawal.status = "completed"

        db.commit()
        db.refresh(withdrawal)
        db.refresh(wallet)

        return withdrawal, current_balance, Decimal(str(wallet.balance or "0")).quantize(Decimal("0.01"))
    except Exception:
        db.rollback()
        raise


def list_withdrawal_requests(
    db: Session,
    worker_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[WithdrawalRequest]:
    return (
        db.query(WithdrawalRequest)
        .filter(WithdrawalRequest.worker_id == worker_id)
        .order_by(WithdrawalRequest.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
