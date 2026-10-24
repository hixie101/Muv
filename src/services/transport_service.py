"""Hong Kong bus ETA client for the KMB and Citybus open-data APIs.

This module is synchronous and has no Qt dependency, so it can be tested on its
own. ``BusService`` runs it on a background thread.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from .errors import TransitError, describe_request_error

log = logging.getLogger(__name__)

# The APIs return timestamps like 2026-10-24T14:06:55+08:00; treat naive ones as HK time.
HKT = timezone(timedelta(hours=8))


def parse_eta(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO ETA string; returns None for missing or malformed values."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=HKT)


class TransitService:
    """Fetches and normalises ETAs for KMB and Citybus stops."""

    KMB_BASE_URL = "https://data.etabus.gov.hk/v1/transport/kmb"
    CTB_BASE_URL = "https://rt.data.gov.hk/v2/transport/citybus"

    def __init__(self, timeout: float = 10.0, session: Optional[requests.Session] = None):
        self.timeout = timeout
        self.session = session or requests.Session()

    def close(self) -> None:
        self.session.close()

    # ---- raw requests --------------------------------------------------
    def _get_data(self, url: str) -> List[Dict[str, Any]]:
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise TransitError(f"request failed ({describe_request_error(exc)})") from exc
        except ValueError as exc:
            raise TransitError("response was not valid JSON") from exc

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise TransitError("response had no 'data' list")
        return data

    def get_kmb_eta(self, stop_id: str, route: str, service_type: int = 1) -> List[Dict[str, Any]]:
        """GET /eta/{stop_id}/{route}/{service_type} on the KMB API."""
        url = (
            f"{self.KMB_BASE_URL}/eta/{quote(str(stop_id), safe='')}"
            f"/{quote(str(route), safe='')}/{int(service_type)}"
        )
        return self._get_data(url)

    def get_ctb_eta(self, stop_id: str, route: str, company_id: str = "CTB") -> List[Dict[str, Any]]:
        """GET /eta/{company_id}/{stop_id}/{route} on the Citybus API."""
        url = (
            f"{self.CTB_BASE_URL}/eta/{quote(company_id, safe='')}"
            f"/{quote(str(stop_id), safe='')}/{quote(str(route), safe='')}"
        )
        return self._get_data(url)

    # ---- normalised view -----------------------------------------------
    def get_unified_eta(
        self,
        operator: str,
        stop_id: str,
        route: str,
        service_type: int = 1,
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Return ETAs for either operator in one common shape.

        Entries without an ETA (for example "last bus departed") are kept with
        ``eta`` and ``minutes`` set to None so the UI can show the remark.
        Raises TransitError if the request fails and ValueError for an unknown operator.
        """
        op = operator.strip().upper()
        if op == "KMB":
            raw = self.get_kmb_eta(stop_id, route, service_type)
            operator_name = "KMB"
        elif op in ("CTB", "CITYBUS"):
            raw = self.get_ctb_eta(stop_id, route)
            operator_name = "CTB"
        else:
            raise ValueError(f"Unsupported operator: {operator}")

        now = now or datetime.now(HKT)
        normalised = []
        for index, item in enumerate(raw):
            eta_text = item.get("eta") or None
            eta = parse_eta(eta_text)
            minutes = None if eta is None else max(0, int((eta - now).total_seconds() // 60))
            normalised.append(
                {
                    "operator": operator_name,
                    "route": route,
                    "stop_id": stop_id,
                    "sequence": item.get("eta_seq") or index + 1,
                    "direction": item.get("dir") or "",
                    "destination": item.get("dest_en") or item.get("dest_tc") or "",
                    "eta": eta_text,
                    "minutes": minutes,
                    "remark": item.get("rmk_en") or item.get("rmk_tc") or "",
                }
            )
        normalised.sort(key=lambda entry: (entry["direction"], entry["sequence"]))
        return normalised
