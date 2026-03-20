# gigshield/backend/app/schemas/zone.py

from pydantic import BaseModel
from datetime import datetime


class ZoneOut(BaseModel):
    zone_id:     str
    name:        str
    city:        str
    centroid_lat: float
    centroid_lng: float
    radius_km:   float
    risk_tier:   str | None

    class Config:
        from_attributes = True


class ZDISnapshotOut(BaseModel):
    zone_id:          str
    zdi_score:        int
    disruption_level: str
    payout_pct:       int
    rain_component:   int | None
    outage_component: int | None
    traffic_component: int | None
    aqi_component:    int | None
    snapshot_at:      datetime

    class Config:
        from_attributes = True