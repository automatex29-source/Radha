"""An English question gets an English answer. Free models answered "Create a picture of a cozy tea stall in
Mumbai at sunset" in Hinglish, with the app language set to English."""
import os
import sys
import time
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def server():
    os.environ.setdefault("MONGO_URL", "mongodb://test")
    import motor.motor_asyncio
    motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
    import embeddings
    embeddings._failed_at = time.monotonic()
    import server as s
    return s


def _said(*texts):
    return [{"role": "user", "content": t} for t in texts]


def test_english_question_gets_the_english_note(server):
    assert server._english_chat(_said("Create a picture of a cozy tea stall in Mumbai at sunset, warm light."))
    assert server._english_chat(_said("Explain how the stock market works"), "en")


def test_hinglish_hindi_and_other_settings_do_not(server):
    assert not server._english_chat(_said("mujhe ek budget plan banao please yaar"))
    assert not server._english_chat(_said("मुझे शेयर बाजार समझाओ"))
    assert not server._english_chat(_said("Explain how the stock market works in Hindi"))
    assert not server._english_chat(_said("Explain how the stock market works"), "hi")
    assert not server._english_chat(_said("ok thanks"))  # too short to tell; the chat's language carries on
