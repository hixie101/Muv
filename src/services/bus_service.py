"""Bus service for Muv: polls KMB / Citybus ETAs on a background thread."""

import logging
import time
from typing import Any, Dict, Optional

from PyQt6.QtCore import pyqtSignal

from .base_service import PollingService
from .errors import ServiceError, TransitError
from .transport_service import TransitService

log = logging.getLogger(__name__)


class BusService(PollingService):
    """Emits ``data_fetched`` with::

        {"arrivals": [...], "errors": [...], "stops_configured": bool, "fetched_at": float}

    Arrivals from all configured stops are merged and sorted soonest first. If only
    some stops fail, the rest are still published and the failures are listed in
    ``errors``. If every stop fails, nothing is emitted and ``error`` fires instead.
    """

    data_fetched = pyqtSignal(object)

    def __init__(self, config, transit: Optional[TransitService] = None):
        interval = config.get("transit.refresh_seconds")
        super().__init__("bus", interval, retry_interval=min(interval, 15))
        self.stops = config.get("transit.stops") or []
        self.transit = transit or TransitService()

    def poll(self) -> Optional[Dict[str, Any]]:
        if not self.stops:
            return {"arrivals": [], "errors": [], "stops_configured": False, "fetched_at": time.time()}

        arrivals, errors = [], []
        for stop in self.stops:
            if self.stopping:
                return None
            label = stop.get("label") or f'{stop["operator"]} {stop["route"]}'
            try:
                etas = self.transit.get_unified_eta(
                    stop["operator"], stop["stop_id"], stop["route"], stop.get("service_type", 1)
                )
            except (TransitError, ValueError) as exc:
                errors.append(f"{label}: {exc}")
                continue
            for eta in etas:
                eta["label"] = stop.get("label", "")
                arrivals.append(eta)

        if errors and not arrivals and len(errors) == len(self.stops):
            raise ServiceError("bus times unavailable (" + "; ".join(errors) + ")")

        arrivals.sort(key=lambda a: (a["minutes"] is None, a["minutes"] or 0, a["route"]))
        return {"arrivals": arrivals, "errors": errors, "stops_configured": True, "fetched_at": time.time()}

    def publish(self, payload: Dict[str, Any]) -> None:
        self.data_fetched.emit(payload)
