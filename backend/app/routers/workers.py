# gigshield/backend/app/routers/workers.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.worker import WorkerRegisterRequest, WorkerOut
from app.services import register_worker, get_worker_by_id

router = APIRouter()


@router.post("/", response_model=WorkerOut, status_code=201)
def register(body: WorkerRegisterRequest, db: Session = Depends(get_db)):
    try:
        worker = register_worker(
            db=db,
            full_name=body.full_name,
            phone=body.phone,
            income_tier=body.income_tier,
            zone_id=body.zone_id,
            platform=body.platform,
            aadhaar=body.aadhaar,
        )
        return worker
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{worker_id}", response_model=WorkerOut)
def get_worker(worker_id: str, db: Session = Depends(get_db)):
    worker = get_worker_by_id(db, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker
