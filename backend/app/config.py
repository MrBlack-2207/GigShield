# gigshield/backend/app/config.py

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):

    # Database
    DATABASE_URL: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str
    CORS_ORIGINS: str = "http://localhost:3000"

    # Insurance constants (match our locked design doc)
    WORKING_HOURS_PER_DAY: float = 10.0
    COVERAGE_RATIO: float = 0.30
    CORRELATION_LOAD: float = 1.18
    LOADING_FACTOR: float = 1.25
    ADMIN_FEE_INR: float = 5.00
    SCHEDULER_INTERVAL_MINUTES: int = 15
    DISRUPTION_FREQ_MODEL_PATH: str = "models/disruption_frequency_model.pkl"
    DISRUPTION_FREQ_CLIP_MIN: float = 0.0
    DISRUPTION_FREQ_CLIP_MAX: float = 4.0
    DISRUPTION_FREQ_LOOKBACK_DAYS: int = 28
    DISRUPTION_FREQ_MIN_POINTS: int = 8

    # Mock flags
    USE_MOCK_WEATHER: bool = True
    USE_MOCK_TRAFFIC: bool = True
    USE_MOCK_AQI: bool = True
    USE_MOCK_PAYMENT: bool = True

    # Event-flag severity weights (stored for transparency; not used in ZDI yet)
    EVENT_WEIGHT_STRIKE: float = 0.80
    EVENT_WEIGHT_BANDH: float = 0.85
    EVENT_WEIGHT_PETROL_CRISIS: float = 0.70
    EVENT_WEIGHT_LOCKDOWN: float = 1.00
    EVENT_WEIGHT_CURFEW: float = 0.90

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    """
    Cached singleton. Import and call this everywhere:
        from app.config import get_settings
        settings = get_settings()
    """
    return Settings()
