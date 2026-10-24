"""Weather service for Muv: polls OpenWeatherMap on a background thread."""

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from PyQt6.QtCore import pyqtSignal

from .base_service import PollingService
from .errors import ConfigurationError, ServiceError, describe_request_error

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ICON_DIR = PROJECT_ROOT / "assets" / "icons" / "weather"

ANIMATIONS = {
    "Clear": "sun",
    "Clouds": "cloud",
    "Rain": "rain",
    "Drizzle": "drizzle",
    "Thunderstorm": "thunder",
    "Snow": "snow",
    "Mist": "mist",
    "Haze": "mist",
    "Fog": "mist",
    "Smoke": "mist",
    "Dust": "mist",
    "Sand": "mist",
    "Ash": "mist",
    "Squall": "wind",
    "Tornado": "wind",
}


class WeatherService(PollingService):
    """Emits ``data_fetched({"current": ..., "forecast": ..., "fetched_at": ...})``.

    ``current`` and ``forecast`` are the raw OpenWeatherMap JSON documents.
    On failure nothing is emitted; ``error`` fires and the UI keeps the last data.
    """

    # object, not dict: PyQt converts dict signal arguments to QVariantMap.
    data_fetched = pyqtSignal(object)

    BASE_URL = "https://api.openweathermap.org/data/2.5"

    def __init__(self, config, session: Optional[requests.Session] = None):
        settings = config.section("weather")
        super().__init__("weather", settings["refresh_seconds"], retry_interval=60)
        self.api_key = str(settings.get("api_key") or "")
        self.city = settings["city"]
        self.units = settings["units"]
        self.timeout = 10
        self.session = session or requests.Session()
        self._last_forecast: Optional[Dict[str, Any]] = None

    def _get(self, endpoint: str) -> Dict[str, Any]:
        params = {"q": self.city, "appid": self.api_key, "units": self.units}
        try:
            response = self.session.get(f"{self.BASE_URL}/{endpoint}", params=params, timeout=self.timeout)
            if response.status_code == 401:
                raise ConfigurationError(
                    "OpenWeatherMap rejected the API key (HTTP 401). "
                    "New keys can take a while to activate."
                )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            # Do not use str(exc): it contains the URL, including the API key.
            raise ServiceError(f"weather request failed ({describe_request_error(exc)})") from exc
        except ValueError as exc:
            raise ServiceError("weather response was not valid JSON") from exc

    def poll(self) -> Optional[Dict[str, Any]]:
        if not self.api_key or self.api_key.startswith("YOUR_"):
            raise ConfigurationError(
                "weather API key not set (weather.api_key or MUV_OPENWEATHER_API_KEY)"
            )

        current = self._get("weather")  # required: failure aborts this poll
        if self.stopping:
            return None
        try:
            self._last_forecast = self._get("forecast")
        except ConfigurationError:
            raise
        except ServiceError as exc:
            # Current conditions are still worth showing; reuse the last forecast.
            log.warning("weather: forecast unavailable, reusing previous (%s)", exc)

        return {"current": current, "forecast": self._last_forecast, "fetched_at": time.time()}

    def publish(self, payload: Dict[str, Any]) -> None:
        self.data_fetched.emit(payload)

    @staticmethod
    def get_weather_icon_path(icon_code: str) -> Optional[Path]:
        """Path to a bundled icon, or None if the project has no such file."""
        path = ICON_DIR / f"{icon_code}.png"
        return path if path.is_file() else None

    @staticmethod
    def get_weather_animation(weather_condition: str) -> str:
        """Animation name for an OpenWeatherMap condition group; "none" if unknown."""
        return ANIMATIONS.get(weather_condition, "none")
