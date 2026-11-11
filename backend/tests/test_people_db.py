"""Account details live in their own database (people_db), and existing accounts are moved there safely.

Offline: MongoDB is mongomock.
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import people_db  # noqa: E402


def _dbs(monkeypatch, **env):
    for k in ("USERS_DB_NAME", "USERS_MONGO_URL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return people_db.connect(mongomock_motor.AsyncMongoMockClient, "mongodb://test", "radha")


def test_account_collections_go_to_their_own_database(monkeypatch):
    dbs = _dbs(monkeypatch)
    assert dbs.separate
    assert dbs.users.database.name == "krish_users"
    assert dbs["password_resets"].database.name == "krish_users"
    assert dbs.logins.database.name == "krish_users"
    assert dbs.messages.database.name == "radha"
    assert dbs["conversations"].database.name == "radha"
    assert dbs.settings.database.name == "radha"


def test_same_name_keeps_everything_in_one_database(monkeypatch):
    dbs = _dbs(monkeypatch, USERS_DB_NAME="radha")
    assert not dbs.separate
    assert dbs.users.database.name == "radha"
    assert asyncio.run(people_db.move_existing_users(dbs)) == 0


def test_existing_accounts_are_copied_once_and_the_old_copy_kept(monkeypatch):
    dbs = _dbs(monkeypatch)

    async def go():
        await dbs.main.users.insert_many([{"id": "a", "email": "a@x.com"}, {"id": "b", "email": "b@x.com"}])
        await dbs.main.logins.insert_one({"userId": "a", "method": "password", "at": "2026-01-01"})
        await dbs.main.password_resets.insert_one({"userId": "b", "tokenHash": "h"})
        assert await people_db.move_existing_users(dbs) == 2
        assert await dbs.users.count_documents({}) == 2
        assert await dbs.logins.count_documents({}) == 1
        assert await dbs.password_resets.count_documents({}) == 1
        assert await dbs.main.users.count_documents({}) == 2  # backup left in place

        # A second start right away (or a second server) copies nothing twice and keeps newer changes.
        await dbs.users.update_one({"id": "a"}, {"$set": {"name": "Asha"}})
        assert await people_db.move_existing_users(dbs) == 0
        assert await dbs.users.count_documents({}) == 2
        assert (await dbs.users.find_one({"id": "a"}))["name"] == "Asha"

        # Someone signed up on the old version while the new one went live: picked up within the hour.
        await dbs.main.users.insert_one({"id": "c", "email": "c@x.com"})
        assert await people_db.move_existing_users(dbs) == 1

        # Long after the move, the old database is no longer looked at.
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await dbs.people.settings.update_one({"id": people_db.MOVED_MARK}, {"$set": {"at": old}})
        await dbs.main.users.insert_one({"id": "d", "email": "d@x.com"})
        assert await people_db.move_existing_users(dbs) == 0
        assert not await dbs.users.find_one({"id": "d"})

    asyncio.run(go())


def test_no_permission_on_new_database_falls_back_to_main(monkeypatch):
    from pymongo.errors import OperationFailure
    dbs = _dbs(monkeypatch)

    class Locked:
        name = "krish_users"

        def __getattr__(self, name):
            raise OperationFailure("not authorized on krish_users", code=13)

        def __getitem__(self, name):
            raise OperationFailure("not authorized on krish_users", code=13)

    dbs._people = Locked()
    assert asyncio.run(people_db.move_existing_users(dbs)) == 0
    assert not dbs.separate
    assert dbs.users.database.name == "radha"


@pytest.fixture(scope="module")
def app():
    for k in ("USERS_DB_NAME", "USERS_MONGO_URL"):
        os.environ.pop(k, None)
    os.environ.update(MONGO_URL="mongodb://test", GROQ_API_KEY="test", AUTOMATIONS_SCHEDULER="0",
                      AI_MODEL="openai/gpt-oss-120b")
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server
    from fastapi.testclient import TestClient
    # An account made before this change, still in the main database.
    asyncio.run(server.db.main.users.insert_one({
        "id": "old-1", "email": "old@test.com", "name": "Meera", "password_hash": server.hash_password("oldpass1"),
        "createdAt": "2025-01-01T00:00:00+00:00", "updatedAt": "2025-01-01T00:00:00+00:00"}))
    with TestClient(server.app) as c:
        yield c, server


def test_existing_account_still_signs_in_after_the_move(app):
    c, server = app
    r = c.post("/api/auth/login", json={"email": "old@test.com", "password": "oldpass1"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["name"] == "Meera"
    assert c.portal.call(server.db.people.users.find_one, {"id": "old-1"})


def test_new_accounts_are_saved_in_the_people_database(app):
    c, server = app
    r = c.post("/api/auth/register", json={"name": "Ravi", "email": "ravi@test.com", "password": "pass1234"})
    assert r.status_code == 200, r.text
    uid = r.json()["user"]["id"]
    assert c.portal.call(server.db.people.users.find_one, {"id": uid})
    assert not c.portal.call(server.db.main.users.find_one, {"id": uid})
    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert me.json()["email"] == "ravi@test.com"


def test_deleting_an_account_also_deletes_the_backup_copy(app):
    c, server = app
    token = c.post("/api/auth/login", json={"email": "old@test.com", "password": "oldpass1"}).json()["token"]
    r = c.post("/api/auth/delete-account", json={"password": "oldpass1"},
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert not c.portal.call(server.db.people.users.find_one, {"id": "old-1"})
    assert not c.portal.call(server.db.main.users.find_one, {"id": "old-1"})
