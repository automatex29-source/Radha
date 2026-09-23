"""File storage for uploaded documents.

On Emergent (EMERGENT_LLM_KEY set) files go to Emergent Object Storage.
Everywhere else they are stored in MongoDB, split into 4MB chunks.
MongoDB holds the canonical file registry either way.
"""
import asyncio
import os
from datetime import datetime, timezone

import requests

APP_NAME = "radha"
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
USE_EMERGENT = bool(EMERGENT_KEY) and os.environ.get("STORAGE_BACKEND", "") != "mongo"
CHUNK_BYTES = 4 * 1024 * 1024

db = None
_storage_key = None


def init(database):
    global db
    db = database


async def ensure_indexes():
    if not USE_EMERGENT:
        await db.storage_objects.create_index("path", unique=True)
        await db.storage_chunks.create_index([("path", 1), ("n", 1)], unique=True)


def object_path(user_id: str, file_id: str, ext: str) -> str:
    return f"{APP_NAME}/uploads/{user_id}/{file_id}.{ext}"


# ------------------------------------------------------ Emergent object storage
def init_storage(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _emergent_put(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data,
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def _emergent_get(path: str) -> tuple[bytes, str]:
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


# ------------------------------------------------------------------ public API
async def put_object(path: str, data: bytes, content_type: str) -> dict:
    if USE_EMERGENT:
        return await asyncio.to_thread(_emergent_put, path, data, content_type)
    await db.storage_chunks.delete_many({"path": path})
    pieces = [data[i:i + CHUNK_BYTES] for i in range(0, len(data), CHUNK_BYTES)] or [b""]
    await db.storage_chunks.insert_many([{"path": path, "n": n, "data": piece} for n, piece in enumerate(pieces)])
    await db.storage_objects.update_one({"path": path}, {"$set": {
        "contentType": content_type, "size": len(data), "createdAt": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"path": path, "size": len(data)}


async def get_object(path: str) -> tuple[bytes, str]:
    if USE_EMERGENT:
        return await asyncio.to_thread(_emergent_get, path)
    meta = await db.storage_objects.find_one({"path": path})
    if not meta:
        raise FileNotFoundError(path)
    chunks = db.storage_chunks.find({"path": path}).sort("n", 1)
    return b"".join([bytes(c["data"]) async for c in chunks]), meta.get("contentType", "application/octet-stream")
