"""Configuration loading and validation for Muv.

Settings come from ``config.json`` in the project root (or the file named by the
``MUV_CONFIG`` environment variable). Anything missing falls back to DEFAULTS.
Secrets can be supplied through environment variables instead of the file.
"""

import copy
import json
import logging
import os
from pathlib import Path
from typing import Any, List

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULTS = {
    "log_level": "INFO",
    "display": {
        "fullscreen": True,
        "hide_cursor": True,
        "fade_ms": 1000,
        "time_format": "%H:%M",
        "date_format": "%A, %d %B %Y",
    },
    "weather": {
        "api_key": "",
        "city": "Hong Kong",
        "units": "metric",
        "refresh_seconds": 600,
    },
    "transit": {
        "refresh_seconds": 30,
        "stops": [],
    },
    "wallpaper": {
        "rotate_seconds": 60,
        "local_dir": "wallpapers",
        "cache_dir": "cache/wallpapers",
        "smb": {
            "enabled": False,
            "server": "",
            "port": 445,
            "share": "",
            "path": "/",
            "username": "",
            "password": "",
            "sync_seconds": 900,
            "max_files": 50,
        },
    },
}

# Environment variable -> config path. Lets secrets stay out of config.json.
ENV_OVERRIDES = {
    "MUV_OPENWEATHER_API_KEY": "weather.api_key",
    "MUV_SMB_PASSWORD": "wallpaper.smb.password",
}

# config path -> smallest allowed value
MINIMUMS = {
    "display.fade_ms": 0,
    "weather.refresh_seconds": 60,
    "transit.refresh_seconds": 10,
    "wallpaper.rotate_seconds": 5,
    "wallpaper.smb.sync_seconds": 60,
    "wallpaper.smb.max_files": 1,
}

SUPPORTED_OPERATORS = {"KMB", "CTB", "CITYBUS"}
PLACEHOLDER_PREFIX = "REPLACE"


class ConfigError(Exception):
    """The configuration file exists but cannot be used."""


def _merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


class ConfigManager:
    def __init__(self, path=None):
        self._warnings: List[str] = []
        self._data = copy.deepcopy(DEFAULTS)
        self.path = Path(path or os.environ.get("MUV_CONFIG") or PROJECT_ROOT / "config.json")
        self._load_file()
        self._apply_env()
        self._validate()

    # ---- loading -------------------------------------------------------
    def _load_file(self) -> None:
        if not self.path.exists():
            self._warnings.append(
                f"No config file at {self.path}; using defaults "
                "(copy config.example.json to config.json)"
            )
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConfigError(f"Cannot read {self.path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ConfigError(f"{self.path}: top level must be a JSON object")
        _merge(self._data, loaded)

    def _apply_env(self) -> None:
        for var, dotted in ENV_OVERRIDES.items():
            value = os.environ.get(var)
            if value:
                self._set(dotted, value)

    # ---- validation ----------------------------------------------------
    def _validate(self) -> None:
        for dotted, minimum in MINIMUMS.items():
            value = self.get(dotted)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
                default = self._lookup(DEFAULTS, dotted)
                self._warnings.append(
                    f"{dotted} must be a number >= {minimum} (got {value!r}); using {default}"
                )
                self._set(dotted, default)

        if not self.get("weather.api_key"):
            self._warnings.append(
                "weather.api_key is empty; set it in config.json or MUV_OPENWEATHER_API_KEY"
            )

        self._set("transit.stops", self._clean_stops(self.get("transit.stops")))
        if not self.get("transit.stops"):
            self._warnings.append("No valid transit stops configured; the bus panel will be empty")

    def _clean_stops(self, stops: Any) -> list:
        if not isinstance(stops, list):
            self._warnings.append("transit.stops must be a list; ignoring it")
            return []
        clean = []
        for index, stop in enumerate(stops):
            where = f"transit.stops[{index}]"
            if not isinstance(stop, dict):
                self._warnings.append(f"{where} must be an object; skipped")
                continue
            operator = str(stop.get("operator", "")).strip().upper()
            stop_id = str(stop.get("stop_id", "")).strip()
            route = str(stop.get("route", "")).strip()
            if operator not in SUPPORTED_OPERATORS:
                self._warnings.append(f"{where}: operator must be KMB or CTB; skipped")
            elif not stop_id or not route:
                self._warnings.append(f"{where}: stop_id and route are required; skipped")
            elif stop_id.upper().startswith(PLACEHOLDER_PREFIX):
                self._warnings.append(f"{where}: stop_id is still the placeholder; skipped")
            else:
                service_type = stop.get("service_type", 1)
                clean.append(
                    {
                        "operator": "KMB" if operator == "KMB" else "CTB",
                        "stop_id": stop_id,
                        "route": route,
                        "service_type": service_type if isinstance(service_type, int) else 1,
                        "label": str(stop.get("label", "")).strip(),
                    }
                )
        return clean

    # ---- access --------------------------------------------------------
    @staticmethod
    def _lookup(data: dict, dotted: str, default: Any = None) -> Any:
        node: Any = data
        for key in dotted.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def _set(self, dotted: str, value: Any) -> None:
        *parents, last = dotted.split(".")
        node = self._data
        for key in parents:
            node = node.setdefault(key, {})
        node[last] = value

    def get(self, dotted: str, default: Any = None) -> Any:
        """Look up a setting by dotted path, e.g. ``config.get("weather.city")``."""
        return self._lookup(self._data, dotted, default)

    def section(self, name: str) -> dict:
        """Return a copy of a top-level section."""
        return copy.deepcopy(self._data.get(name, {}))

    def resolve_path(self, value) -> Path:
        """Resolve a path from the config; relative paths are relative to the project root."""
        path = Path(str(value)).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path

    def warnings(self) -> List[str]:
        """Problems found while loading; log these at startup."""
        return list(self._warnings)
