"""Answers that keep being written after the browser goes away (like Claude).

A reply used to be written only while the browser that asked was reading it: closing the tab, switching
apps on a phone or losing the connection stopped it. Now each reply runs as its own background job on the
server. The browser that asked just follows it; any other browser or device signed in to the same account
can follow it too (`follow`), from the start or from where it left off, and the finished reply is saved to
the chat as before. Only Stop (`stop`) ends a reply early.

The jobs live in this process's memory (the app runs as one process). When the server shuts down (a new
deploy or a restart), every running reply is stopped so the part already written is saved to the chat
instead of being lost. In case the process is killed before that can happen, the text written so far is
also kept on the chat every few seconds (`liveDraft`), and `recover` turns a left-over draft into a saved,
stopped reply when the server starts again.
"""
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, Optional

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 15
KEEP_FINISHED_SECONDS = 120  # a finished reply can still be replayed for a while (a device that reconnects late)
MAX_BUFFER_BYTES = 6_000_000  # past this, live code previews are no longer kept for replay (the text still is)
DRAFT_EVERY_SECONDS = 4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LiveTurn:
    def __init__(self, conv_id: str, user_id: str):
        self.conv_id = conv_id
        self.user_id = user_id
        self.events: list = []  # every SSE event written so far, each ending in a blank line
        self.size = 0
        self.text = ""  # the reply's text so far, for the saved draft
        self.done = False
        self.started = time.time()
        self.started_iso = _now()
        self.finished = 0.0
        self.task: Optional[asyncio.Task] = None
        self._changed = asyncio.Event()

    def add(self, chunk: str) -> None:
        for part in chunk.split("\n\n"):
            if not part.strip() or all(line.startswith(":") for line in part.split("\n") if line):
                continue  # keepalive comments are not kept; followers get their own
            if self.size > MAX_BUFFER_BYTES and part.startswith("event: code_draft"):
                continue
            self.events.append(part + "\n\n")
            self.size += len(part)
            if part.startswith("data:"):  # a piece of the reply's text (named events start with "event:")
                try:
                    piece = json.loads("".join(line[5:].strip() for line in part.split("\n") if line.startswith("data:")))
                except ValueError:
                    piece = None
                if isinstance(piece, str):
                    self.text += piece
        self._wake()

    def finish(self) -> None:
        self.done = True
        self.finished = time.time()
        self._wake()

    def _wake(self) -> None:
        self._changed.set()
        self._changed = asyncio.Event()

    async def wait(self, timeout: float) -> None:
        changed = self._changed
        try:
            await asyncio.wait_for(changed.wait(), timeout)
        except asyncio.TimeoutError:
            pass


_TURNS: Dict[str, LiveTurn] = {}


def _tidy() -> None:
    now = time.time()
    for key, turn in list(_TURNS.items()):
        if turn.done and now - turn.finished > KEEP_FINISHED_SECONDS:
            _TURNS.pop(key, None)


def get(conv_id: str, user_id: str) -> Optional[LiveTurn]:
    turn = _TURNS.get(conv_id)
    return turn if turn and turn.user_id == user_id else None


def running(conv_id: str, user_id: str) -> bool:
    turn = get(conv_id, user_id)
    return bool(turn and not turn.done)


async def _save_draft(db, turn: LiveTurn) -> None:
    try:
        await db.conversations.update_one({"id": turn.conv_id}, {"$set": {"liveDraft": {
            "text": turn.text, "userId": turn.user_id, "startedAt": turn.started_iso, "updatedAt": _now()}}})
    except Exception:
        logger.warning("saving the reply's draft failed", exc_info=True)


async def _run(db, turn: LiveTurn, gen) -> None:
    saved_at = time.time()
    try:
        async for chunk in gen:
            turn.add(chunk)
            if db is not None and turn.text and time.time() - saved_at > DRAFT_EVERY_SECONDS:
                saved_at = time.time()
                await _save_draft(db, turn)
    except asyncio.CancelledError:
        pass  # Stop or a shutdown: the reply's own cleanup has saved the part written
    except Exception:
        logger.exception("background reply failed")
        turn.add('event: error\ndata: "Something went wrong while writing the answer"\n\n')
    finally:
        try:
            await gen.aclose()
        except Exception:
            logger.exception("closing a background reply failed")
        if db is not None:  # the reply has saved itself to the chat; the draft is no longer needed
            try:
                await db.conversations.update_one({"id": turn.conv_id, "liveDraft.startedAt": turn.started_iso},
                                                  {"$unset": {"liveDraft": ""}})
            except Exception:
                logger.warning("clearing the reply's draft failed", exc_info=True)
        turn.finish()


async def start(db, conv_id: str, user_id: str, gen) -> LiveTurn:
    """Run a reply stream as a background job. A reply still running in the same chat is stopped first."""
    _tidy()
    old = _TURNS.get(conv_id)
    if old and not old.done:
        await stop(conv_id, old.user_id)
    turn = LiveTurn(conv_id, user_id)
    _TURNS[conv_id] = turn
    turn.task = asyncio.create_task(_run(db, turn, gen))
    return turn


async def follow(turn: LiveTurn, after: int = 0) -> AsyncIterator[str]:
    """The reply's events from number `after` on, then each new one as it is written, until it ends.

    Leaving (closing the tab, losing the connection) only stops following; the reply goes on.
    """
    i = max(0, after)
    while True:
        while i < len(turn.events):
            yield turn.events[i]
            i += 1
        if turn.done:
            return
        await turn.wait(KEEPALIVE_SECONDS)
        if i >= len(turn.events) and not turn.done:
            yield ": keepalive\n\n"


async def stop(conv_id: str, user_id: str, wait: float = 10) -> bool:
    """Stop a running reply (the Stop button); the part already written is saved. True if one was running."""
    turn = get(conv_id, user_id)
    if not turn or turn.done or not turn.task:
        return False
    turn.task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(turn.task), wait)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass
    return True


async def stop_all(wait: float = 8) -> None:
    """On shutdown: stop every running reply so what each has written is saved."""
    tasks = [t.task for t in _TURNS.values() if not t.done and t.task]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.wait(tasks, timeout=wait)


async def recover(db) -> int:
    """At startup: a draft left on a chat means the server stopped mid-reply without saving it. Save the
    part that was written as a stopped reply (Regenerate finishes it), unless the reply did get saved."""
    count = 0
    async for conv in db.conversations.find({"liveDraft.startedAt": {"$exists": True}}, {"id": 1, "liveDraft": 1, "model": 1}):
        draft = conv.get("liveDraft") or {}
        try:
            last = await db.messages.find_one({"conversationId": conv["id"]}, sort=[("createdAt", -1)])
            saved = last and last.get("role") == "assistant" and (last.get("createdAt") or "") >= (draft.get("startedAt") or "")
            if (draft.get("text") or "").strip() and not saved:
                await db.messages.insert_one({
                    "id": str(uuid.uuid4()), "conversationId": conv["id"], "role": "assistant",
                    "content": draft["text"], "model": conv.get("model"), "stopped": True, "createdAt": _now()})
                count += 1
            await db.conversations.update_one({"id": conv["id"]}, {"$unset": {"liveDraft": ""}})
        except Exception:
            logger.exception("recovering a reply's draft failed")
    return count
