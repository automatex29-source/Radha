"""Offline tests for the free image providers and the slideshow video fallback."""
import asyncio
import io
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import media  # noqa: E402
from agent import slideshow, video  # noqa: E402

KEYS = ("IMAGE_PROVIDER", "OPENAI_API_KEY", "POLLINATIONS_API_KEY", "HF_TOKEN", "VIDEO_PROVIDER",
        "GEMINI_API_KEY", "GOOGLE_API_KEY")


def run(coro):
    return asyncio.run(coro)


def png(color="red", size=(96, 64)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def fake_http(monkeypatch, handler):
    real = httpx.AsyncClient

    def client(*a, **kw):
        kw.pop("transport", None)
        return real(*a, transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(httpx, "AsyncClient", client)


class TestImages:
    def test_provider_order(self, monkeypatch):
        assert media._image_providers() == ["pollinations", "pollinations_legacy"]
        assert media.image_available()
        monkeypatch.setenv("HF_TOKEN", "h")
        monkeypatch.setenv("OPENAI_API_KEY", "o")
        assert media._image_providers() == ["openai", "huggingface", "pollinations", "pollinations_legacy"]
        monkeypatch.setenv("IMAGE_PROVIDER", "off")
        assert not media.image_available()

    def test_image_type(self):
        assert media.image_type(png()) == "image/png"
        assert media.image_type(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
        assert media.image_type(b"<html>") == ""

    def test_pollinations_with_key(self, monkeypatch):
        monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")
        seen = []

        def handler(req):
            seen.append(req)
            return httpx.Response(200, content=png(), headers={"content-type": "image/png"})

        fake_http(monkeypatch, handler)
        assert media.image_type(run(media.generate_image("a red fox", "1536x1024"))) == "image/png"
        req = seen[0]
        assert req.url.host == "gen.pollinations.ai" and req.url.raw_path.startswith(b"/image/a%20red%20fox?")
        assert req.headers["authorization"] == "Bearer sk_test"
        assert req.url.params["width"] == "1536" and req.url.params["height"] == "1024"

    def test_falls_back_to_keyless_endpoint(self, monkeypatch):
        hosts = []

        def handler(req):
            hosts.append(req.url.host)
            if req.url.host == "gen.pollinations.ai":
                return httpx.Response(401, json={"error": "key required"})
            return httpx.Response(200, content=png())

        fake_http(monkeypatch, handler)
        assert run(media.generate_image("cat")) == png()
        assert hosts == ["gen.pollinations.ai", "image.pollinations.ai"]

    def test_all_fail_reports_errors(self, monkeypatch):
        fake_http(monkeypatch, lambda req: httpx.Response(200, text="<html>busy</html>",
                                                          headers={"content-type": "text/html"}))
        with pytest.raises(media.ImageError, match="not an image"):
            run(media.generate_image("cat"))


class TestSlideshow:
    def test_scene_prompts(self):
        assert len(slideshow.scene_prompts("a dragon", None, 12)) == 4
        assert len(slideshow.scene_prompts("a dragon", None, 60)) == slideshow.MAX_SCENES
        got = slideshow.scene_prompts("x", ["dawn over hills", " ", "dragon lands"], 12)
        assert len(got) == 2 and got[0].startswith("dawn over hills.")

    @pytest.mark.skipif(not slideshow.ffmpeg_path(), reason="ffmpeg not available")
    def test_makes_real_mp4(self, monkeypatch):
        colors = iter(["red", "green", "blue"])

        async def fake_image(prompt, size="1024x1024", quality=None):
            return png(next(colors), (300, 200))

        monkeypatch.setattr(media, "generate_image", fake_image)
        monkeypatch.setattr(slideshow, "LONG_SIDE", 320)
        data = run(slideshow.make_slideshow("x", 6, scenes=["a", "b", "c"]))
        assert data[4:8] == b"ftyp"
        path = Path(__file__).parent / "_slideshow_test.mp4"
        path.write_bytes(data)
        try:
            info = subprocess.run([slideshow.ffmpeg_path(), "-i", str(path)], capture_output=True, text=True).stderr
        finally:
            path.unlink()
        assert "Duration: 00:00:06" in info and "320x180" in info

    def test_no_images_is_an_error(self, monkeypatch):
        async def broken(prompt, size="1024x1024", quality=None):
            raise media.ImageError("down")

        monkeypatch.setattr(media, "generate_image", broken)
        with pytest.raises(slideshow.SlideshowError, match="down"):
            run(slideshow.make_slideshow("x", 6))


class TestVideoFallback:
    def test_pollinations_video(self, monkeypatch):
        monkeypatch.setenv("POLLINATIONS_API_KEY", "sk")
        seen = []

        def handler(req):
            seen.append(req)
            return httpx.Response(200, content=b"MP4", headers={"content-type": "video/mp4"})

        fake_http(monkeypatch, handler)
        out = run(video.generate("waves", 12, "portrait"))
        assert out["method"] == "ai_video" and out["data"] == b"MP4"
        assert seen[0].url.path == "/video/waves" and seen[0].url.params["aspectRatio"] == "9:16"
        assert seen[0].url.params["duration"] == "5"

    def test_out_of_budget_falls_back_to_slideshow(self, monkeypatch):
        monkeypatch.setenv("POLLINATIONS_API_KEY", "sk")
        fake_http(monkeypatch, lambda req: httpx.Response(402, json={"error": "budget"}))

        async def fake_slideshow(prompt, seconds, portrait, scenes):
            return b"SLIDES"

        monkeypatch.setattr(slideshow, "make_slideshow", fake_slideshow)
        out = run(video.generate("waves"))
        assert out["method"] == "slideshow" and out["data"] == b"SLIDES" and "allowance" in out["note"]
