# gigshield/data/workers_seed.py
# Run with: docker exec gigshield_backend python /app/../data/workers_seed.py

import sys
sys.path.insert(0, "/app")

from app.database import SessionLocal
from app.models.dark_store import DarkStore
from app.models.worker import Worker
from app.models.policy import Policy
from app.engine.premium_calculator import calculate_premium, get_current_season
from datetime import date, datetime, timezone, timedelta

WORKERS = [
    # High earners — ₹800/day
    {"full_name": "Ravi Kumar",    "phone": "9880001001", "income_tier": 800,
     "zone_id": "BLR-01", "platform": "zepto"},
    {"full_name": "Suresh Babu",   "phone": "9880001002", "income_tier": 800,
     "zone_id": "BLR-03", "platform": "blinkit"},

    # Mid earners — ₹600/day
    {"full_name": "Anitha Raj",    "phone": "9880001003", "income_tier": 600,
     "zone_id": "BLR-02", "platform": "zepto"},
    {"full_name": "Mohammed Arif", "phone": "9880001004", "income_tier": 600,
     "zone_id": "BLR-06", "platform": "blinkit"},

    # Entry earners — ₹400/day
    {"full_name": "Kavya Nair",    "phone": "9880001005", "income_tier": 400,
     "zone_id": "BLR-04", "platform": "zepto"},
    {"full_name": "Deepak Singh",  "phone": "9880001006", "income_tier": 400,
     "zone_id": "BLR-05", "platform": "zepto"},
]

db = SessionLocal()
season = get_current_season()

for w in WORKERS:
    existing = db.query(Worker).filter(Worker.phone == w["phone"]).first()
    if existing:
        print(f"  SKIP  {w['full_name']} (already exists)")
        continue

    store = (
        db.query(DarkStore)
        .filter(
            DarkStore.zone_id == w["zone_id"],
            DarkStore.platform == w["platform"],
        )
        .first()
    )
    if not store:
        print(f"  SKIP  {w['full_name']} (no dark store for {w['zone_id']} / {w['platform']})")
        continue

    worker = Worker(
        full_name=w["full_name"],
        phone=w["phone"],
        income_tier=w["income_tier"],
        primary_zone_id=w["zone_id"],
        platform=w["platform"],
        home_store_id=store.id,
        kyc_status="VERIFIED",
        is_active=True,
    )
    db.add(worker)
    db.flush()  # get worker_id before policy

    # Give each worker an ACTIVE policy
    breakdown = calculate_premium(w["income_tier"], season)
    today     = date.today()

    # Lookback set to the PAST so claims fire immediately in demo
    policy = Policy(
        worker_id=worker.worker_id,
        zone_id=w["zone_id"],
        income_tier=w["income_tier"],
        weekly_premium_inr=breakdown.weekly_premium_inr,
        coverage_ratio=breakdown.coverage_ratio,
        weekly_payout_cap=breakdown.weekly_payout_cap_inr,
        season_at_purchase=season,
        week_start=today,
        week_end=today + timedelta(days=7),
        status="ACTIVE",
        # Lookback already expired — claims will not be blocked
        lookback_exclusion_until=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(policy)
    print(f"  OK    {w['full_name']} | ₹{w['income_tier']}/day | {w['zone_id']} | premium ₹{breakdown.weekly_premium_inr}/week")

db.commit()
db.close()
print("\nWorkers and policies seeded.")
