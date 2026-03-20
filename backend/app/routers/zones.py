# gigshield/backend/app/routers/zones.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.zone import ZoneOut, ZDISnapshotOut
from app.services import (
    get_all_zones, get_zone_by_id,
    get_latest_zdi, get_all_latest_zdis,
)

router = APIRouter()


@router.get("/", response_model=list[ZoneOut])
def list_zones(db: Session = Depends(get_db)):
    return get_all_zones(db)


@router.get("/heatmap", response_model=list[ZDISnapshotOut])
def heatmap(db: Session = Depends(get_db)):
    """Latest ZDI for every zone — used by the map screen."""
    return get_all_latest_zdis(db)


@router.get("/{zone_id}", response_model=ZoneOut)
def get_zone(zone_id: str, db: Session = Depends(get_db)):
    zone = get_zone_by_id(db, zone_id)
    if not zone:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


@router.get("/{zone_id}/zdi", response_model=ZDISnapshotOut)
def get_zone_zdi(zone_id: str, db: Session = Depends(get_db)):
    snapshot = get_latest_zdi(db, zone_id)
    if not snapshot:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No ZDI data for this zone yet")
    return snapshot
