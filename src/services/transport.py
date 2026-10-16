import httpx
from typing import List, Dict, Any, Optional

class TransitService:
    """
    A unified service to fetch transit data from Hong Kong bus operators:
    - KMB (Kowloon Motor Bus) via official OpenAPI
    - CTB (Citybus) via official OpenAPI V2
    """
    def __init__(self, timeout: float = 10.0):
        self.kmb_base_url = "https://data.etabus.gov.hk/v1/transport/kmb"
        self.ctb_base_url = "https://data.gov.hk"
        self.timeout = timeout

    async def get_kmb_eta(self, stop_id: str, route: str, service_type: int = 1) -> List[Dict[str, Any]]:
        """
        Fetches ETA for a given KMB stop, route, and service type.
        Endpoint: /eta/{stop_id}/{route}/{service_type}
        """
        url = f"{self.kmb_base_url}/eta/{stop_id}/{route}/{service_type}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.json().get("data", [])
            except httpx.HTTPError:
                return []

    async def get_ctb_eta(self, stop_id: str, route: str, company_id: str = "CTB") -> List[Dict[str, Any]]:
        """
        Fetches ETA for a given Citybus stop and route.
        Endpoint: /eta/{company_id}/{stop_id}/{route}
        """
        url = f"{self.ctb_base_url}/eta/{company_id}/{stop_id}/{route}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.json().get("data", [])
            except httpx.HTTPError:
                return []

    async def get_unified_eta(self, operator: str, stop_id: str, route: str) -> List[Dict[str, Any]]:
        """
        A normalized method returning standard arrival info for either operator.
        """
        op = operator.upper()
        raw_eta_list = []
        
        if op == "KMB":
            raw_eta_list = await self.get_kmb_eta(stop_id, route)
        elif op in ("CTB", "CITYBUS"):
            raw_eta_list = await self.get_ctb_eta(stop_id, route)
        else:
            raise ValueError(f"Unsupported operator: {operator}")

        normalized = []
        for index, item in enumerate(raw_eta_list):
            eta_time_str = item.get("eta") or item.get("ETA")
            eta_seq = item.get("eta_seq") or (index + 1)
            dest = item.get("dest_en") or item.get("dest_tc")
            
            normalized.append({
                "operator": "KMB" if op == "KMB" else "CTB",
                "route": route,
                "stop_id": stop_id,
                "sequence": eta_seq,
                "destination": dest,
                "eta": eta_time_str,  # ISO format timestamp string
                "rmk": item.get("rmk_en") or item.get("rmk") or ""
            })
            
        return normalized
