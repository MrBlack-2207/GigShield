from __future__ import annotations

import logging
import math
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

MODEL_PATH = Path("models/disruption_severity_model.pkl")
ALLOWED_PAYOUT_RATES = (0.40, 0.70, 1.00)


def _is_close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(float(a) - float(b)) <= tol


@lru_cache(maxsize=1)
def _load_severity_artifact():
    model_path = MODEL_PATH
    if not model_path.is_absolute():
        model_path = Path.cwd() / model_path
    model_path = model_path.resolve()

    with model_path.open("rb") as f:
        artifact = pickle.load(f)

    model = artifact
    class_to_payout_rate: dict[int, float] | None = None
    feature_columns: list[str] | None = None

    if isinstance(artifact, dict):
        model = artifact.get("model")
        raw_mapping = artifact.get("class_to_payout_rate")
        if isinstance(raw_mapping, dict):
            class_to_payout_rate = {int(k): float(v) for k, v in raw_mapping.items()}
        raw_features = artifact.get("feature_columns")
        if isinstance(raw_features, list):
            feature_columns = [str(c) for c in raw_features]

    if model is None:
        raise ValueError("severity_model_missing_in_artifact")

    logger.info(
        "severity_model_loaded event=severity_model_loaded path=%s",
        str(model_path),
    )
    return model, class_to_payout_rate, feature_columns, str(model_path)


def _normalize_predicted_rate(
    pred: Any,
    class_to_payout_rate: dict[int, float] | None,
) -> tuple[float | None, str | None]:
    mapping = class_to_payout_rate or {0: 0.40, 1: 0.70, 2: 1.00}

    # Class-label prediction path (expected for multiclass model).
    if isinstance(pred, (int, float)) and float(pred).is_integer():
        label = int(float(pred))
        if label in mapping and any(_is_close(mapping[label], allowed) for allowed in ALLOWED_PAYOUT_RATES):
            return float(mapping[label]), None
        return None, f"invalid_predicted_class:{label}"

    # Direct payout-rate prediction path (defensive compatibility).
    try:
        raw_rate = float(pred)
    except (TypeError, ValueError):
        return None, "non_numeric_prediction"

    if not math.isfinite(raw_rate):
        return None, "non_finite_prediction"

    for allowed in ALLOWED_PAYOUT_RATES:
        if _is_close(raw_rate, allowed):
            return float(allowed), None
    return None, f"unsupported_predicted_rate:{raw_rate}"


def predict_disruption_severity(features: dict[str, Any]) -> dict[str, Any]:
    """
    Predict payout-rate severity using trained multiclass model.

    Returns:
    {
      "payout_rate": float | None,
      "source": "ml" | "fallback",
      "error": optional_string,
      "model_path": optional_string,
      "raw_prediction": optional_any
    }
    """
    if not isinstance(features, dict):
        error = "features must be a dict"
        logger.warning(
            "severity_inference_fallback event=severity_inference_fallback reason=%s",
            error,
        )
        return {"payout_rate": None, "source": "fallback", "error": error}

    try:
        model, class_to_payout_rate, feature_columns, model_path = _load_severity_artifact()
    except Exception as exc:
        error = f"model_load_failed:{exc}"
        logger.warning(
            "severity_inference_fallback event=severity_inference_fallback reason=%s",
            error,
        )
        return {"payout_rate": None, "source": "fallback", "error": error}

    try:
        if feature_columns:
            feature_row = {name: features.get(name, 0.0) for name in feature_columns}
            feature_df = pd.DataFrame([feature_row], columns=feature_columns)
        else:
            feature_df = pd.DataFrame([features])

        raw_pred = model.predict(feature_df)[0]
        payout_rate, normalize_error = _normalize_predicted_rate(raw_pred, class_to_payout_rate)
        if payout_rate is None:
            logger.warning(
                "severity_inference_fallback event=severity_inference_fallback reason=%s",
                normalize_error,
            )
            return {
                "payout_rate": None,
                "source": "fallback",
                "error": normalize_error,
                "model_path": model_path,
                "raw_prediction": raw_pred,
            }

        logger.info(
            "severity_inference_success event=severity_inference_success model_path=%s payout_rate=%.2f",
            model_path,
            payout_rate,
        )
        return {
            "payout_rate": float(payout_rate),
            "source": "ml",
            "model_path": model_path,
            "raw_prediction": raw_pred,
        }
    except Exception as exc:
        error = f"inference_failed:{exc}"
        logger.warning(
            "severity_inference_fallback event=severity_inference_fallback reason=%s",
            error,
        )
        return {"payout_rate": None, "source": "fallback", "error": error}
