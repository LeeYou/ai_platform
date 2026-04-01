"""Router: /api/v1/capabilities - Proxy to train service for capability list"""

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/capabilities", tags=["capabilities"])

TRAIN_SERVICE_URL = os.getenv("TRAIN_SERVICE_URL", "http://train:8001")


@router.get("", response_model=list[dict[str, Any]])
async def list_capabilities():
    """Fetch capability list from train service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{TRAIN_SERVICE_URL}/api/v1/capabilities/")
            response.raise_for_status()
            capabilities = response.json()

            # Extract just the name field for the license UI
            return [{"name": cap["name"]} for cap in capabilities]
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Train service error: {e.response.text}"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to train service: {str(e)}"
        )
