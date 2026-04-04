import json
import random
from copy import deepcopy

import redis as redis_lib

from app.config import get_settings

settings = get_settings()

_STATE_PREFIX = "mock_signal_state"
_STATE_TTL_SECONDS = 60 * 60 * 24 * 7
_fallback_state: dict[str, dict] = {}
_redis_client = None
_redis_init_failed = False


def _state_key(signal_type: str, zone_id: str) -> str:
    return f"{_STATE_PREFIX}:{signal_type}:{zone_id}"


def _get_redis_client():
    global _redis_client, _redis_init_failed

    if _redis_client is not None:
        return _redis_client
    if _redis_init_failed:
        return None

    try:
        _redis_client = redis_lib.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_init_failed = True
        return None


def load_state(signal_type: str, zone_id: str, default_state: dict) -> dict:
    key = _state_key(signal_type, zone_id)
    redis_client = _get_redis_client()

    if redis_client is not None:
        try:
            payload = redis_client.get(key)
            if payload:
                data = json.loads(payload)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass

    state = _fallback_state.get(key)
    if state is not None:
        return deepcopy(state)
    return deepcopy(default_state)


def save_state(signal_type: str, zone_id: str, state: dict) -> None:
    key = _state_key(signal_type, zone_id)
    payload = json.dumps(state)

    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            redis_client.setex(key, _STATE_TTL_SECONDS, payload)
        except Exception:
            pass

    _fallback_state[key] = deepcopy(state)


def maybe_shift_trend(current_trend: int, change_probability: float = 0.20) -> int:
    if random.random() >= change_probability:
        return current_trend
    return random.choice([-1, 0, 1])


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
