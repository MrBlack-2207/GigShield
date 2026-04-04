from __future__ import annotations

import logging
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

MODEL_PATH = Path("models/disruption_duration_model.pkl")
MIN_AFFECTED_HOURS = 0.25
MAX_AFFECTED_HOURS = 10.0
FALLBACK_AFFECTED_HOURS = 4.0


def _clip_hours(value: float) -> float:
    return max(MIN_AFFECTED_HOURS, min(MAX_AFFECTED_HOURS, float(value)))


def _avg_hours_fraction(affected_hours: float) -> float:
    working_hours = float(settings.WORKING_HOURS_PER_DAY)
    if working_hours <= 0:
        working_hours = 10.0
    return float(affected_hours) / working_hours


def _fallback_payload(error: str | None = None) -> dict[str, Any]:
    affected = _clip_hours(FALLBACK_AFFECTED_HOURS)
    payload: dict[str, Any] = {
        "affected_hours": round(affected, 4),
        "avg_hours_fraction": round(_avg_hours_fraction(affected), 6),
        "source": "fallback",
    }
    if error:
        payload["error"] = error
    return payload


@lru_cache(maxsize=1)
def _load_duration_model():
    model_path = MODEL_PATH
    if not model_path.is_absolute():
        model_path = Path.cwd() / model_path
    model_path = model_path.resolve()

    with model_path.open("rb") as f:
        model = pickle.load(f)

    logger.info(
        "duration_model_loaded event=duration_model_loaded path=%s",
        str(model_path),
    )
    return model, str(model_path)


def predict_disruption_duration(features: dict) -> dict[str, Any]:
    """
    Predict disruption duration (affected_hours) from a feature dict.

    Returns:
    {
      "affected_hours": float,
      "avg_hours_fraction": float,
      "source": "ml" | "fallback",
      "error": optional_string
    }
    """
    if not isinstance(features, dict):
        error = "features must be a dict"
        logger.warning(
            "duration_inference_fallback event=duration_inference_fallback reason=%s",
            error,
        )
        return _fallback_payload(error=error)

    try:
        model, model_path = _load_duration_model()
    except Exception as exc:
        error = f"model_load_failed:{exc}"
        logger.warning(
            "duration_inference_fallback event=duration_inference_fallback reason=%s",
            error,
        )
        return _fallback_payload(error=error)

    try:
        feature_df = pd.DataFrame([features])
        pred = float(model.predict(feature_df)[0])
        affected = _clip_hours(pred)
        payload = {
            "affected_hours": round(affected, 4),
            "avg_hours_fraction": round(_avg_hours_fraction(affected), 6),
            "source": "ml",
        }
        logger.info(
            "duration_inference_success event=duration_inference_success model_path=%s affected_hours=%.4f",
            model_path,
            affected,
        )
        return payload
    except Exception as exc:
        error = f"inference_failed:{exc}"
        logger.warning(
            "duration_inference_fallback event=duration_inference_fallback reason=%s",
            error,
        )
        return _fallback_payload(error=error)
