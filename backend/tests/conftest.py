"""Shared test setup."""
import os
import sys

import pytest

# Spam protection (rate limits, email DNS checks) is tested on its own in test_launch_growth.py.
os.environ.setdefault("ABUSE_LIMITS", "off")
os.environ.setdefault("EMAIL_DNS_CHECK", "off")


@pytest.fixture(autouse=True, scope="module")
def _fresh_server_per_module():
    """Each test module that imports `server` gets a fresh copy, with its own (mock) database.

    The server binds its database client to the event loop of the first TestClient that starts it; reusing that
    copy in the next module failed with "Event loop is closed" and left data from earlier modules behind.
    """
    sys.modules.pop("server", None)
    yield
    sys.modules.pop("server", None)
