# gigshield/backend/app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import get_settings
from app.scheduler.jobs import start_scheduler, stop_scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="GigShield — Parametric Insurance for Gig Workers",
    description="Hyperlocal income-loss protection for Zepto/Blinkit delivery partners in Bengaluru.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import workers, policies, zones, claims, admin, wallet, contract

app.include_router(workers.router,  prefix="/api/workers",  tags=["Workers"])
app.include_router(policies.router, prefix="/api/policies", tags=["Policies"])
app.include_router(zones.router,    prefix="/api/zones",    tags=["Zones"])
app.include_router(claims.router,   prefix="/api/claims",   tags=["Claims"])
app.include_router(admin.router,    prefix="/api/admin",    tags=["Admin"])
app.include_router(wallet.router,   prefix="/api/wallet",   tags=["Wallet"])
app.include_router(contract.router, prefix="/api/contract", tags=["DemoContract"])


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "mocks": {
            "weather": settings.USE_MOCK_WEATHER,
            "traffic": settings.USE_MOCK_TRAFFIC,
            "aqi":     settings.USE_MOCK_AQI,
            "payment": settings.USE_MOCK_PAYMENT,
        }
    }
