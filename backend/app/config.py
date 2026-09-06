"""Runtime configuration read from environment variables.

Kubernetes injects MONGODB_DATABASE / MONGODB_COLLECTION from the ``app-config`` ConfigMap and
MONGODB_URI from the ``backend-mongodb-uri`` Secret. Error messages raised here never contain
the URI, so they are safe to log.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_DATABASE = "cruddb"
DEFAULT_COLLECTION = "items"
_ALLOWED_SCHEMES = ("mongodb://", "mongodb+srv://")


class ConfigError(ValueError):
    """Raised when required configuration is missing or malformed."""


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str
    mongodb_database: str = DEFAULT_DATABASE
    mongodb_collection: str = DEFAULT_COLLECTION
    mongodb_connect_timeout_ms: int = 2000
    mongodb_server_selection_timeout_ms: int = 2000
    mongodb_ping_timeout_ms: int = 2000
    startup_index_timeout_ms: int = 5000
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source: Mapping[str, str] = os.environ if env is None else env
        uri = source.get("MONGODB_URI", "").strip()
        if not uri:
            raise ConfigError("MONGODB_URI is required")
        if not uri.startswith(_ALLOWED_SCHEMES):
            raise ConfigError("MONGODB_URI must start with mongodb:// or mongodb+srv://")
        return cls(
            mongodb_uri=uri,
            mongodb_database=_non_empty(source, "MONGODB_DATABASE", DEFAULT_DATABASE),
            mongodb_collection=_non_empty(source, "MONGODB_COLLECTION", DEFAULT_COLLECTION),
            mongodb_connect_timeout_ms=_positive_int(source, "MONGODB_CONNECT_TIMEOUT_MS", 2000),
            mongodb_server_selection_timeout_ms=_positive_int(
                source, "MONGODB_SERVER_SELECTION_TIMEOUT_MS", 2000
            ),
            mongodb_ping_timeout_ms=_positive_int(source, "MONGODB_PING_TIMEOUT_MS", 2000),
            startup_index_timeout_ms=_positive_int(source, "STARTUP_INDEX_TIMEOUT_MS", 5000),
            log_level=_non_empty(source, "LOG_LEVEL", "INFO").upper(),
        )


def _non_empty(source: Mapping[str, str], key: str, default: str) -> str:
    value = source.get(key, "").strip()
    return value or default


def _positive_int(source: Mapping[str, str], key: str, default: int) -> int:
    raw = source.get(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{key} must be a positive integer") from None
    if value <= 0:
        raise ConfigError(f"{key} must be a positive integer")
    return value
