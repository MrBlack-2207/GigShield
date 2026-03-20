# gigshield/backend/app/routers/claims.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.claim import ClaimOut
from app.services import get_worker_claims
from app.models.claim import Claim

router = APIRouter()


@router.get("/worker/{worker_id}", response_model=list[ClaimOut])
def get_claims_for_worker(worker_id: str, db: Session = Depends(get_db)):
    return get_worker_claims(db, worker_id)


@router.get("/{claim_id}", response_model=ClaimOut)
def get_claim(claim_id: str, db: Session = Depends(get_db)):
    claim = db.query(Claim).filter(Claim.claim_id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim
