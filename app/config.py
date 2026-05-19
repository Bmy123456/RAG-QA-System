import os
import yaml
from pathlib import Path
from functools import lru_cache

CONFIG_DIR = Path(__file__).parent.parent / "config"


def _expand_env(value: str) -> str:
    """Replace ${VAR} with environment variable values."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def _expand_envs(data: dict) -> dict:
    """Recursively expand env vars in config dict."""
    result = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = _expand_envs(value)
        elif isinstance(value, str):
            result[key] = _expand_env(value)
        else:
            result[key] = value
    return result


@lru_cache()
def get_config() -> dict:
    with open(CONFIG_DIR / "settings.yaml", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _expand_envs(raw)
