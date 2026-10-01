"""fal.ai queue API: premium image and video models (Nano Banana Pro, Veo 3.1) with one FAL_KEY.

Submit to https://queue.fal.run/{model}, poll the status URL until it is
COMPLETED, read the result, then download the file it points to. fal bills per
image / per second of video against prepaid credit on the fal account.
"""
import asyncio
import os
import time
from typing import Optional

import httpx

QUEUE = os.environ.get("FAL_QUEUE_URL", "https://queue.fal.run").rstrip("/")
POLL_SECONDS = 3
TIMEOUT_SECONDS = int(os.environ.get("FAL_TIMEOUT_SECONDS", "600"))


class FalError(Exception):
    pass


def configured() -> bool:
    return bool(os.environ.get("FAL_KEY"))


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=20.0), follow_redirects=True,
                             headers={"Authorization": f"Key {os.environ.get('FAL_KEY', '')}"})


def _error(resp: httpx.Response) -> str:
    try:
        detail = resp.json().get("detail") or resp.json()
    except Exception:
        detail = resp.text
    return f"fal HTTP {resp.status_code}: {str(detail)[:300]}"


async def run(model: str, payload: dict, timeout: Optional[int] = None) -> dict:
    """Run a model through the queue and return its JSON result."""
    async with _client() as client:
        resp = await client.post(f"{QUEUE}/{model}", json=payload)
        if resp.status_code >= 400:
            raise FalError(_error(resp))
        job = resp.json()
        status_url = job.get("status_url") or f"{QUEUE}/{model}/requests/{job['request_id']}/status"
        response_url = job.get("response_url") or f"{QUEUE}/{model}/requests/{job['request_id']}"
        deadline = time.monotonic() + (timeout or TIMEOUT_SECONDS)
        while True:
            status = await client.get(status_url)
            if status.status_code >= 400:
                raise FalError(_error(status))
            state = status.json().get("status")
            if state == "COMPLETED":
                break
            if state not in ("IN_QUEUE", "IN_PROGRESS"):
                raise FalError(f"fal job ended with status {state}: {str(status.json())[:300]}")
            if time.monotonic() > deadline:
                raise FalError("fal job timed out")
            await asyncio.sleep(POLL_SECONDS)
        result = await client.get(response_url)
        if result.status_code >= 400:
            raise FalError(_error(result))
        return result.json()


async def download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code >= 400:
            raise FalError(f"download failed: HTTP {resp.status_code}")
        return resp.content
