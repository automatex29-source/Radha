"""People's account details live in their own database, apart from chats, apps and everything else.

Which collections count as account details: USER_COLLECTIONS (the accounts themselves, password-reset links and
the sign-in history). They are kept in USERS_DB_NAME (default "krish_users"), on the same MongoDB server unless
USERS_MONGO_URL points somewhere else. Everything else stays in DB_NAME as before.

The rest of the code keeps writing `db.users`, `db.messages` and so on: `Databases` sends each name to the right
database, so nothing else had to change.

Moving existing accounts: on startup `move_existing_users` copies any accounts still in the main database into the
new one (safely if two copies of the server start together; see move_existing_users). The old copy is left where it was as a
backup. If the MongoDB login can't write to the new database (a user limited to one database), the server says so in
the log and keeps account details in the main database, so sign-in never breaks.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError, OperationFailure

log = logging.getLogger("people_db")

USER_COLLECTIONS = frozenset({"users", "password_resets", "logins"})
MOVED_MARK = "users_moved_to_own_db"
# For this long after the first move, each start copies again anything new in the main database: while a new version
# is going live, the old one keeps running for a few minutes and can still sign people up there.
CATCH_UP = timedelta(hours=1)


def users_db_name() -> str:
    return (os.environ.get("USERS_DB_NAME") or "").strip() or "krish_users"


class Databases:
    """Looks like one Motor database; account collections come from `people`, the rest from `main`."""

    def __init__(self, main, people):
        self._main = main
        self._people = people

    @property
    def main(self):
        return self._main

    @property
    def people(self):
        return self._people

    @property
    def separate(self) -> bool:
        return self._people is not self._main

    def use_main_for_people(self) -> None:
        self._people = self._main

    def _pick(self, name: str):
        return self._people if name in USER_COLLECTIONS else self._main

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._pick(name), name)

    def __getitem__(self, name: str):
        return self._pick(name)[name]


def connect(client_cls, mongo_url: str, main_name: str) -> Databases:
    main = client_cls(mongo_url)[main_name]
    people_url = (os.environ.get("USERS_MONGO_URL") or "").strip()
    people_name = users_db_name()
    if not people_url and people_name == main_name:
        return Databases(main, main)
    people_client = client_cls(people_url) if people_url else main.client
    return Databases(main, people_client[people_name])


async def move_existing_users(dbs: Databases) -> int:
    """Copy accounts (and their reset links and sign-in history) from the main database into the people database.

    The first time, everything is copied and a mark in the people database's settings records when. Starts within
    CATCH_UP of that copy again whatever is new; later starts do nothing. Copying keeps each record's _id, so a record
    already there (copied earlier, or by another server starting at the same time) is skipped, never doubled or
    overwritten. Returns how many accounts were copied.
    """
    if not dbs.separate:
        return 0
    main, people = dbs.main, dbs.people
    now = datetime.now(timezone.utc)
    try:
        mark = await people.settings.find_one({"id": MOVED_MARK})
        if mark and now - datetime.fromisoformat(mark["at"]) > CATCH_UP:
            return 0
        moved = 0
        for name in sorted(USER_COLLECTIONS):
            async for doc in main[name].find({}):
                try:
                    await people[name].insert_one(doc)
                    moved += name == "users"
                except DuplicateKeyError:
                    pass
        if not mark:
            try:
                await people.settings.insert_one({"id": MOVED_MARK, "at": now.isoformat()})
            except DuplicateKeyError:
                pass
        if moved:
            log.warning("Moved %s accounts into the %s database (the old copy in %s is kept as a backup).",
                        moved, people.name, main.name)
        return moved
    except OperationFailure as e:
        if e.code in (13, 8000) or "not authorized" in str(e).lower():  # 13 = Unauthorized; 8000 = Atlas
            log.error("Can't write to the %s database with this MongoDB login, so account details stay in %s. "
                      "Give the login readWrite on %s (or set USERS_DB_NAME=%s) to silence this.",
                      people.name, main.name, people.name, main.name)
            dbs.use_main_for_people()
            return 0
        raise


async def forget_old_copy(dbs: Databases, user_id: str) -> None:
    """When an account is deleted, delete its backup copy in the main database too."""
    if dbs.separate:
        await dbs.main.users.delete_one({"id": user_id})
        for name in USER_COLLECTIONS - {"users"}:
            await dbs.main[name].delete_many({"userId": user_id})
