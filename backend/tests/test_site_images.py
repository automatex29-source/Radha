"""AI pictures for built sites: link rewriting, caching, limits and the fallback photo."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import site_images  # noqa: E402


def test_rewrite_html_css_and_sizes():
    html = ('<img src="https://krish-image.invalid/chocolate-truffle-cake-on-marble.jpg?w=810&h=600" alt="x">'
            "<div style=\"background-image:url('https://krish-image.invalid/bakery-interior.webp')\"></div>")
    out = site_images.rewrite(html)
    assert 'src="/api/site-image?prompt=chocolate%20truffle%20cake%20on%20marble&w=808&h=600"' in out
    assert "url('/api/site-image?prompt=bakery%20interior&w=800&h=600')" in out  # default size
    assert site_images.rewrite(html, "https://k.example").count("https://k.example/api/site-image") == 2
    assert site_images.rewrite("no pictures") == "no pictures"


@pytest.fixture
def client(monkeypatch):
    mongomock_motor = pytest.importorskip("mongomock_motor")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    site_images.init(mongomock_motor.AsyncMongoMockClient()["t"])
    made = []

    async def make(prompt, w, h):
        made.append((prompt, w, h))
        if "broken" in prompt:
            raise RuntimeError("provider down")
        await asyncio.sleep(0.05)
        return b"RIFF....WEBPfake"

    monkeypatch.setattr(site_images, "_make", make)
    monkeypatch.setattr(site_images, "_recent", {})
    monkeypatch.setattr(site_images, "_day", {"date": "", "count": 0})
    app = FastAPI()
    app.include_router(site_images.router)
    c = TestClient(app)
    c.made = made
    return c


def test_picture_is_made_once_then_cached(client):
    r1 = client.get("/api/site-image", params={"prompt": "red velvet cake", "w": 400, "h": 300})
    r2 = client.get("/api/site-image", params={"prompt": "Red velvet cake", "w": 400, "h": 300})
    assert r1.status_code == r2.status_code == 200 and r1.content == r2.content
    assert r1.headers["content-type"] == "image/webp" and "immutable" in r1.headers["cache-control"]
    assert client.made == [("red velvet cake", 400, 304)]


def test_failure_and_limits_fall_back_to_a_keyword_photo(client, monkeypatch):
    r = client.get("/api/site-image", params={"prompt": "broken mango dessert photo"}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://loremflickr.com/800/600/broken,mango")
    monkeypatch.setattr(site_images, "PER_IP_HOUR", 1)
    client.get("/api/site-image", params={"prompt": "first"})
    r = client.get("/api/site-image", params={"prompt": "second cake"}, follow_redirects=False)
    assert r.status_code == 302 and "loremflickr" in r.headers["location"]


def test_cache_is_trimmed(client, monkeypatch):
    monkeypatch.setattr(site_images, "MAX_CACHED", 2)
    for i in range(4):
        client.get("/api/site-image", params={"prompt": f"cake {i}"})
    assert asyncio.run(site_images.db.site_images.count_documents({})) == 2
