import asyncio
import json

import live_search
import search_modes
from agent import web


def test_openalex_rebuilds_abstract_and_meta():
    data = {"results": [{
        "display_name": "CRISPR in crops", "publication_year": 2024, "cited_by_count": 12,
        "primary_location": {"landing_page_url": "https://doi.org/10.1/x", "source": {"display_name": "Nature Plants"}},
        "authorships": [{"author": {"display_name": "A. Rao"}}],
        "abstract_inverted_index": {"Gene": [0], "editing": [1], "works": [2]},
    }, {"display_name": "No link", "primary_location": {}}]}
    out = search_modes.parse_openalex(data, 5)
    assert len(out) == 1
    assert out[0]["url"] == "https://doi.org/10.1/x"
    assert out[0]["snippet"].startswith("A. Rao, 2024, Nature Plants, cited 12 times. Gene editing works")


def test_youtube_ids():
    assert search_modes.youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1") == "dQw4w9WgXcQ"
    assert search_modes.youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert search_modes.youtube_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert search_modes.youtube_id("https://www.youtube.com/@channel") == ""


def test_video_focus_gives_thumbnails(monkeypatch):
    async def fake(query, limit):
        assert "site:youtube.com" in query
        return [{"title": "Review", "url": "https://www.youtube.com/watch?v=abcdefghijk", "snippet": "s"},
                {"title": "Channel", "url": "https://www.youtube.com/@x", "snippet": ""}]
    monkeypatch.setattr(web, "search", fake)
    found = asyncio.run(live_search.gather(["pixel 10 review"], focus="video"))
    assert found["sources"] == [{"type": "video", "title": "Review", "url": "https://www.youtube.com/watch?v=abcdefghijk",
                                 "domain": "youtube.com", "snippet": "s",
                                 "thumbnail": "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"}]
    assert "YouTube videos" in found["context"]


def test_bing_images_parser():
    m = json.dumps({"murl": "https://img.test/full.jpg", "turl": "https://tse.mm.bing.net/th?id=1",
                    "purl": "https://site.test/page", "t": "Taj Mahal"}).replace('"', "&quot;")
    page = f'<div><a class="iusc" m="{m}" href="#">x</a><a class="iusc" m="bad">y</a></div>'
    assert search_modes.parse_bing_images(page, 5) == [{"type": "image", "thumbnail": "https://tse.mm.bing.net/th?id=1",
                                                        "image": "https://img.test/full.jpg",
                                                        "url": "https://site.test/page", "title": "Taj Mahal"}]


def test_commons_parser_keeps_photos_only():
    data = {"query": {"pages": {
        "1": {"index": 2, "title": "File:Taj Mahal.jpg", "imageinfo": [{"thumburl": "https://u/t.jpg", "url": "https://u/f.jpg", "descriptionurl": "https://c/File"}]},
        "2": {"index": 1, "title": "File:Map.svg", "imageinfo": [{"thumburl": "https://u/m.png"}]},
    }}}
    out = search_modes.parse_commons(data, 5)
    assert [o["title"] for o in out] == ["Taj Mahal"]


def test_wants_images():
    assert search_modes.wants_images("show me the taj mahal")
    assert search_modes.wants_images("who is virat kohli")
    assert not search_modes.wants_images("tata motors share price")


def test_pro_search_reads_pages(monkeypatch):
    async def fake_pro(question, model, **k):
        return {"queries": [question, "tata ev sales 2026"],
                "results": [{"title": "EV sales", "url": "https://a.test/ev", "snippet": "Long page text"}]}
    monkeypatch.setattr(search_modes, "pro", fake_pro)
    found = asyncio.run(live_search.gather(["how are tata ev sales"], pro=True, model="m"))
    assert found["queries"] == ["how are tata ev sales", "tata ev sales 2026"]
    assert found["sources"][0]["url"] == "https://a.test/ev" and "Long page text" in found["context"]


def test_images_join_forced_web_search(monkeypatch):
    async def fake_search(query, limit):
        return [{"title": "Taj", "url": "https://t.test", "snippet": "s"}]

    async def fake_images(query, limit):
        return [{"type": "image", "thumbnail": "https://i/t", "image": "https://i/f", "url": "https://p", "title": ""}]
    monkeypatch.setattr(web, "search", fake_search)
    monkeypatch.setattr(search_modes, "images", fake_images)
    found = asyncio.run(live_search.gather(["show me the taj mahal"], force=True))
    assert [s["type"] for s in found["sources"]] == ["web", "image"]
