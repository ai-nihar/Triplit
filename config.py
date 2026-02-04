from __future__ import annotations

import os


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JSON_SORT_KEYS = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


def get_config(name: str | None = None):
    """Return a config class based on FLASK_CONFIG or the provided name."""
    selected = (name or os.getenv("FLASK_CONFIG") or "development").strip().lower()
    if selected == "production":
        return ProductionConfig
    return DevelopmentConfig
