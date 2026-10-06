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
from agent import slideshow, styles, video  # noqa: E402

KEYS = ("FAL_KEY", "IMAGE_PROVIDER", "OPENAI_API_KEY", "POLLINATIONS_API_KEY", "HF_TOKEN", "VIDEO_PROVIDER",
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
        assert media._image_providers() == ["pollinations_legacy"]
        assert media.image_available()
        monkeypatch.setenv("HF_TOKEN", "h")
        monkeypatch.setenv("OPENAI_API_KEY", "o")
        assert media._image_providers() == ["openai", "huggingface", "pollinations_legacy"]
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
            return httpx.Response(200, content=png(size=(768, 512)), headers={"content-type": "image/png"})

        fake_http(monkeypatch, handler)
        assert media.image_type(run(media.generate_image("a red fox", "1536x1024"))) == "image/png"
        req = seen[0]
        assert req.url.host == "gen.pollinations.ai" and req.url.raw_path.startswith(b"/image/a%20red%20fox?")
        assert req.headers["authorization"] == "Bearer sk_test"
        assert req.url.params["width"] == "1536" and req.url.params["height"] == "1024"
        assert req.url.params["model"] == "bytedance/seedream-4.0"  # the better model first

    def test_out_of_free_pollen_uses_the_fast_model(self, monkeypatch):
        monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test")
        models = []

        def handler(req):
            models.append(req.url.params["model"])
            if req.url.params["model"] == "bytedance/seedream-4.0":
                return httpx.Response(402, json={"error": "Insufficient pollen balance"})
            return httpx.Response(200, content=png(size=(768, 768)), headers={"content-type": "image/png"})

        fake_http(monkeypatch, handler)
        assert media.image_type(run(media.generate_image("a red fox"))) == "image/png"
        assert models == ["bytedance/seedream-4.0", "tongyi-mai/z-image-turbo"]

    def test_placeholder_banner_is_rejected(self, monkeypatch):
        fake_http(monkeypatch, lambda req: httpx.Response(200, content=png("green", (400, 120))))
        with pytest.raises(media.ImageError, match="placeholder.*POLLINATIONS_API_KEY"):
            run(media.generate_image("cat", "1024x1024"))

    def test_falls_back_to_keyless_endpoint(self, monkeypatch):
        monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_bad")
        hosts = []

        def handler(req):
            hosts.append(req.url.host)
            if req.url.host == "gen.pollinations.ai":
                return httpx.Response(401, json={"error": "key required"})
            return httpx.Response(200, content=png(size=(512, 512)))

        fake_http(monkeypatch, handler)
        assert run(media.generate_image("cat")) == png(size=(512, 512))
        assert hosts == ["gen.pollinations.ai", "gen.pollinations.ai", "image.pollinations.ai"]  # both models, then keyless

    def test_all_fail_reports_errors(self, monkeypatch):
        fake_http(monkeypatch, lambda req: httpx.Response(200, text="<html>busy</html>",
                                                          headers={"content-type": "text/html"}))
        with pytest.raises(media.ImageError, match="not an image.*POLLINATIONS_API_KEY"):
            run(media.generate_image("cat"))


class TestSlideshow:
    def test_scene_prompts(self):
        assert len(slideshow.scene_prompts("a dragon", None, 12)) == 3
        assert len(slideshow.scene_prompts("a dragon", None, 60)) == slideshow.MAX_SCENES
        got = slideshow.scene_prompts("x", ["dawn over hills", " ", "dragon lands"], 12)
        assert len(got) == 2 and got[0].startswith("dawn over hills.")
        ad = slideshow.scene_prompts("running shoes", None, 12, "ad")
        assert len(ad) == 5 and "hero shot of the product" in ad[0] and "advertising" in ad[0]
        assert "Pixar" in slideshow.scene_prompts("a fox", None, 12, "3d_animation")[0]

    def test_styles(self):
        assert styles.styled_image_prompt("a cat", "anime").startswith("a cat. anime key visual")
        assert styles.styled_image_prompt("a cat", "nope") == "a cat"
        assert styles.video_style("Social Reel")["portrait"]
        assert styles.video_style("unknown") is styles.VIDEO_STYLES["movie"]
        assert "cinematic" not in styles.video_style_names()

    def test_style_names_are_forgiving(self):
        assert styles.normalize("3D Pixar", styles.IMAGE_STYLES) == "3d_animation"
        assert styles.normalize("Sci-Fi", styles.IMAGE_STYLES) == "sci_fi"
        assert styles.normalize("cinematic poster", styles.IMAGE_STYLES) == "cinematic"
        assert styles.normalize("TikTok", styles.VIDEO_STYLES) == "social_reel"
        assert styles.normalize("vaporwave", styles.IMAGE_STYLES) == ""
        assert "Pixar" in styles.styled_image_prompt("a fox", "Pixar")

    def test_tool_schemas_have_no_enums(self):
        from agent.tools import default_registry

        for tool in default_registry()._tools.values():
            if tool.name in ("generate_image", "generate_video"):
                assert all("enum" not in p for p in tool.parameters["properties"].values())

    def test_command_uses_style_transitions_letterbox_and_captions(self):
        cmd = slideshow.build_command("ffmpeg", ["a", "b", "c"], "out.mp4", 3.0, False, "movie",
                                      [None, "cap.png", None])
        graph = cmd[cmd.index("-filter_complex") + 1]
        assert "transition=fadeblack" in graph and "drawbox" in graph and "overlay" in graph
        assert cmd.count("-loop") == 1 and "cap.png" in cmd
        reel = slideshow.build_command("ffmpeg", ["a", "b"], "o", 3.0, True, "social_reel")
        assert "drawbox" not in reel[reel.index("-filter_complex") + 1]

    @pytest.mark.skipif(not slideshow.ffmpeg_path(), reason="ffmpeg not available")
    def test_makes_real_mp4(self, monkeypatch):
        colors = iter(["red", "green", "blue"])

        async def fake_image(prompt, size="1024x1024", quality=None, seed=None):
            return png(next(colors), (300, 200))

        monkeypatch.setattr(media, "generate_image", fake_image)
        monkeypatch.setattr(slideshow, "LONG_SIDE", 320)
        data = run(slideshow.make_slideshow("x", 6, scenes=["a", "b", "c"], style="ad", captions=["Hi", "", "Buy"]))
        assert data[4:8] == b"ftyp"
        path = Path(__file__).parent / "_slideshow_test.mp4"
        path.write_bytes(data)
        try:
            info = subprocess.run([slideshow.ffmpeg_path(), "-i", str(path)], capture_output=True, text=True).stderr
        finally:
            path.unlink()
        assert "Duration: 00:00:06" in info and "320x180" in info

    def test_no_images_is_an_error(self, monkeypatch):
        async def broken(prompt, size="1024x1024", quality=None, seed=None):
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

        async def fake_slideshow(prompt, seconds, portrait, scenes, style, captions):
            return b"SLIDES"

        monkeypatch.setattr(slideshow, "make_slideshow", fake_slideshow)
        out = run(video.generate("waves"))
        assert out["method"] == "slideshow" and out["data"] == b"SLIDES" and "allowance" in out["note"]


class TestToolCallRetry:
    def test_retries_rejected_tool_call(self, monkeypatch):
        from agent import llm

        calls = []

        async def once(model, messages, tools, think=False):
            calls.append(1)
            if len(calls) == 1:
                yield {"type": "heartbeat"}
                raise RuntimeError("GroqException - Tool call validation failed: /style must be one of")
            yield {"type": "text", "text": "ok"}

        monkeypatch.setattr(llm, "_stream_once", once)

        async def collect():
            return [e async for e in llm.stream_completion("m", [], [])]

        assert run(collect())[-1] == {"type": "text", "text": "ok"} and len(calls) == 2

    def test_other_errors_are_not_retried(self, monkeypatch):
        from agent import llm

        async def once(model, messages, tools, think=False):
            raise RuntimeError("boom")
            yield

        monkeypatch.setattr(llm, "_stream_once", once)

        async def collect():
            return [e async for e in llm.stream_completion("m", [], [])]

        with pytest.raises(RuntimeError, match="boom"):
            run(collect())


class TestPromptBoost:
    def fake_llm(self, monkeypatch, answer):
        from agent import llm, prompt_boost

        async def stream(model, messages, tools):
            if isinstance(answer, Exception):
                raise answer
            yield {"type": "text", "text": answer}

        monkeypatch.setattr(llm, "stream_completion", stream)
        monkeypatch.setattr(llm, "configured", lambda m: True)
        return prompt_boost

    def test_image_prompt_is_rewritten(self, monkeypatch):
        pb = self.fake_llm(monkeypatch, "A majestic tiger walking through neon rain at night, low angle, 85mm lens, "
                                        "wet reflections, cinematic teal and magenta light, ultra detailed fur")
        out = run(pb.image_prompt("tiger in rain", "anime"))
        assert out.startswith("A majestic tiger") and "anime key visual" in out

    def test_failure_keeps_original(self, monkeypatch):
        pb = self.fake_llm(monkeypatch, RuntimeError("rate limited"))
        assert run(pb.image_prompt("tiger", "photo")).startswith("tiger. professional photograph")

    def test_video_scenes_share_character(self, monkeypatch):
        pb = self.fake_llm(monkeypatch, 'Sure! {"character": "red-haired girl in a yellow raincoat", '
                                        '"scenes": ["She runs to the bus.", "She waves goodbye."]}')
        assert run(pb.video_scenes("girl", None, "anime", 2)) == [
            "She runs to the bus. red-haired girl in a yellow raincoat",
            "She waves goodbye. red-haired girl in a yellow raincoat"]

    def test_disabled_without_model_key(self, monkeypatch):
        from agent import llm, prompt_boost

        monkeypatch.setattr(llm, "configured", lambda m: False)
        assert run(prompt_boost.video_scenes("x", None, "", 3)) is None


class TestTextFree:
    """Free image models can't spell, so pictures are steered away from any writing."""

    def test_strips_quoted_words_and_negatives(self):
        import media

        out = media.text_free('woman holding a smartphone showing "JON2Video", no text, no logos. photo')
        assert "JON2Video" not in out and "no text" not in out.lower() and "no logos" not in out.lower()
        assert "abstract color" in out

    def test_blank_signs(self):
        import media

        assert "plain, smooth and blank" in media.text_free("a shop with a big sign")
        assert "abstract color" not in media.text_free("a tiger in the rain")

    def test_asks_for_text(self):
        import media

        assert media.asks_for_text('poster with the title "Diwali Sale"')
        assert media.asks_for_text("a mug with the word love on it")
        assert not media.asks_for_text("a dog named Max on a beach")

    def test_free_boost_is_text_free(self, monkeypatch):
        for k in ("FAL_KEY", "OPENAI_API_KEY"):
            monkeypatch.delenv(k, raising=False)
        pb = TestPromptBoost().fake_llm(monkeypatch, 'A founder holds a phone showing the "JON2Video" app at a '
                                                     "sunny desk, 50mm lens, soft window light, warm tones")
        out = run(pb.image_prompt("social media automation app", "photo"))
        assert "JON2Video" not in out and "abstract color" in out

    def test_text_kept_when_asked(self, monkeypatch):
        for k in ("FAL_KEY", "OPENAI_API_KEY"):
            monkeypatch.delenv(k, raising=False)
        pb = TestPromptBoost().fake_llm(monkeypatch, 'A bold festive poster with the title "Diwali Sale" in gold '
                                                     "letters over glowing diyas, rich colors, centered layout")
        assert '"Diwali Sale"' in run(pb.image_prompt('poster with the title "Diwali Sale"', "poster"))

    def test_premium_model_may_write(self, monkeypatch):
        monkeypatch.setenv("FAL_KEY", "k")
        pb = TestPromptBoost().fake_llm(monkeypatch, 'A founder holds a phone showing the "Krish" app at a sunny '
                                                     "desk, 50mm lens, soft window light, warm tones")
        assert '"Krish"' in run(pb.image_prompt("phone with our Krish app", "photo"))

    def test_deck_prompt_is_text_free(self):
        import deck_images

        out = deck_images.ai_prompt({"title": "Use Case: Social Media Automation",
                                     "image_prompt": 'Marketer scheduling posts on a phone app called "JON2Video"'})
        assert "JON2Video" not in out and "abstract color" in out


class TestFal:
    def handler(self, seen, result, final_bytes):
        def handle(req):
            seen.append((req.method, str(req.url)))
            if req.method == "POST":
                assert req.headers["authorization"] == "Key fk"
                return httpx.Response(200, json={"request_id": "r1",
                                                 "status_url": "https://queue.fal.run/m/requests/r1/status",
                                                 "response_url": "https://queue.fal.run/m/requests/r1"})
            if req.url.path.endswith("/status"):
                return httpx.Response(200, json={"status": "COMPLETED"})
            if req.url.host == "queue.fal.run":
                return httpx.Response(200, json=result)
            return httpx.Response(200, content=final_bytes)
        return handle

    def test_image_uses_fal_first(self, monkeypatch):
        monkeypatch.setenv("FAL_KEY", "fk")
        monkeypatch.setattr(__import__("fal_api"), "POLL_SECONDS", 0)
        seen = []
        fake_http(monkeypatch, self.handler(seen, {"images": [{"url": "https://cdn.fal/x.png"}]},
                                            png(size=(300, 200))))
        assert media._image_providers()[0] == "fal"
        assert media.image_type(run(media.generate_image("a castle", "1536x1024"))) == "image/png"
        assert seen[0][1].startswith("https://queue.fal.run/fal-ai/nano-banana-pro")

    def test_video_uses_veo_and_falls_back(self, monkeypatch):
        monkeypatch.setenv("FAL_KEY", "fk")
        monkeypatch.setattr(__import__("fal_api"), "POLL_SECONDS", 0)
        seen, broke = [], []
        ok = self.handler(seen, {"video": {"url": "https://cdn.fal/v.mp4"}}, b"MP4")
        fake_http(monkeypatch, lambda req: httpx.Response(403, json={"detail": "Exhausted balance"}) if broke
                  else ok(req))
        assert video.provider() == "fal"
        out = run(video.generate("a dragon over mountains", 12, "portrait"))
        assert out == {"data": b"MP4", "contentType": "video/mp4", "method": "ai_video"}
        assert "veo3.1/fast" in seen[0][1]

        broke.append(True)

        async def fake_slideshow(prompt, seconds, portrait, scenes, style, captions):
            return b"SLIDES"

        monkeypatch.setattr(slideshow, "make_slideshow", fake_slideshow)
        out = run(video.generate("waves"))
        assert out["method"] == "slideshow" and "premium" in out["note"]
