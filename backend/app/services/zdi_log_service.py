from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.zone_zdi_log import ZoneZDILog

ZDI_THRESHOLD = 25.0
SLOT_MINUTES = 15
WORKING_HOURS_PER_DAY = 10.0


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_affected_hours(
    db: Session,
    zone_id: str,
    start_time: datetime,
    end_time: datetime,
) -> dict[str, Any]:
    """
    Calculates affected hours by counting 15-minute intervals where ZDI >= 25.
    Returns affected hours plus transparency details.
    """
    start_time = _to_utc(start_time)
    end_time = _to_utc(end_time)

    rows = (
        db.query(ZoneZDILog)
        .filter(
            ZoneZDILog.zone_id == zone_id,
            ZoneZDILog.timestamp >= start_time,
            ZoneZDILog.timestamp < end_time,
        )
        .order_by(ZoneZDILog.timestamp.asc())
        .all()
    )

    impacted_rows = [r for r in rows if float(r.zdi_value) >= ZDI_THRESHOLD]
    impacted_count = len(impacted_rows)
    affected_hours = (impacted_count * SLOT_MINUTES) / 60.0
    max_zdi = max((float(r.zdi_value) for r in rows), default=0.0)

    return {
        "zone_id": zone_id,
        "start_time": start_time,
        "end_time": end_time,
        "affected_hours": round(affected_hours, 2),
        "max_zdi": round(max_zdi, 2),
        "timestamps": [r.timestamp for r in impacted_rows],
        "zdi_values": [float(r.zdi_value) for r in impacted_rows],
    }


def get_daily_affected_hours(
    db: Session,
    zone_id: str,
    day: date,
) -> dict[str, Any]:
    """
    Calculates affected hours for one calendar day using 10 working hours.
    """
    if isinstance(day, datetime):
        day = day.date()

    start_time = datetime.combine(day, time.min).replace(tzinfo=timezone.utc)
    end_time = start_time + timedelta(days=1)

    affected = get_affected_hours(db, zone_id, start_time, end_time)
    affected["date"] = day
    affected["working_hours"] = WORKING_HOURS_PER_DAY

    return affected
