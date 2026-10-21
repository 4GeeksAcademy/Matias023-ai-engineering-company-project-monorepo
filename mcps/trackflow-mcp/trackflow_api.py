"""Cliente HTTP privado para los endpoints existentes de TrackFlow."""

import os
from typing import Any

import httpx


class TrackFlowAPI:
    """Acceso a TrackFlow usando un JWT autorizado por solicitud."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("TRACKFLOW_API_URL")
            or "http://127.0.0.1:8000"
        ).rstrip("/")
        self.timeout = timeout

    async def _request(
        self,
        method: str,
        path: str,
        token: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not token or not token.strip():
            return {"ok": False, "reason": "unauthorized"}

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                follow_redirects=False,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                    params=params,
                )

            if response.status_code in (401, 403):
                return {"ok": False, "reason": "unauthorized"}

            if response.status_code == 404:
                return {"ok": False, "reason": "not_found"}

            if response.status_code == 400:
                return {"ok": False, "reason": "invalid_request"}

            if response.status_code >= 300:
                return {"ok": False, "reason": "backend_error"}

            data = response.json()

            if not isinstance(data, (dict, list)):
                return {"ok": False, "reason": "invalid_response"}

            return {"ok": True, "data": data}

        except (httpx.RequestError, ValueError):
            return {"ok": False, "reason": "backend_unavailable"}

    async def get_incident(self, incident_id: int, token: str):
        return await self._request(
            "GET", f"/api/incidents/{incident_id}", token
        )

    async def list_incidents(
        self,
        token: str,
        filters: dict[str, str] | None = None,
    ):
        return await self._request(
            "GET", "/api/incidents", token, params=filters
        )

    async def create_incident(
        self,
        payload: dict[str, Any],
        token: str,
    ):
        return await self._request(
            "POST", "/api/incidents", token, payload=payload
        )

    async def update_incident_status(
        self,
        incident_id: int,
        status: str,
        token: str,
    ):
        return await self._request(
            "PATCH",
            f"/api/incidents/{incident_id}/status",
            token,
            payload={"status": status},
        )

    async def list_products(self, token: str):
        return await self._request(
            "GET", "/inventory/products", token
        )

    async def get_product(self, product_id: int, token: str):
        return await self._request(
            "GET", f"/inventory/products/{product_id}", token
        )
