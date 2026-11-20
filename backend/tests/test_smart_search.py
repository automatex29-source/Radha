"""Krish decides on its own when to search, searches with a cleaner query, reads the top pages, merges two
engines, and picks better YouTube videos."""
import asyncio
import datetime

import live_search
import search_modes
from agent import web
from agent.tools import ToolContext, default_registry


def test_searches_on_its_own_for_facts_that_change():
    for q in ["who is the ceo of tata motors", "best phones under 20000", "latest iphone price",
              "kitna hai gold ka rate", "who won the match yesterday", "what is the top speed of Vande Bharat",
              "how to apply for passport", "IPL 2026 winner", "summarise today's news", "Mumbai mein aaj baarish hogi kya"]:
        assert live_search.auto_search(q), q


def test_no_search_where_it_only_slows_the_answer():
    for q in ["hi", "thanks", "write a poem about rain", "tell me a joke", "explain how a rainbow forms",
              "what is photosynthesis", "why is the sky blue", "what is Krish AI", "who made you",
              "how do I center a div", "```print(1)``` fix this", "meaning of serendipity"]:
        assert not live_search.auto_search(q), q


def test_search_query_drops_chat_words_and_adds_the_year():
    today = datetime.date(2026, 11, 12)
    assert live_search.search_query("pls tell me latest iphone price bro", today) == "latest iphone price 2026"
    assert live_search.search_query("hey krish who is the ceo of tata motors?", today) == "who is the ceo of tata motors"
    assert live_search.search_query("best phones under 20000 in 2025", today) == "best phones under 20000 in 2025"
    assert live_search.search_query("how to make banana shake please?", today) == "how to make banana shake"


def test_video_query():
    assert live_search.video_query("can you show me a video on how to tie a tie") == "how to tie a tie"
    assert live_search.video_query("paneer butter masala kaise banaye") == "paneer butter masala kaise banaye in hindi"
    assert live_search.video_query("suggest youtube videos for learning guitar") == "learning guitar"


def test_merge_ranks_pages_both_engines_found_first():
    ddg = [{"title": "A", "url": "https://a.test/x", "snippet": "a"},
           {"title": "B", "url": "https://www.b.test/y/", "snippet": "short"},
           {"title": "P", "url": "https://pinterest.com/p", "snippet": ""}]
    bing = [{"title": "C", "url": "https://c.test/z", "snippet": "c"},
            {"title": "B", "url": "http://b.test/y?utm_source=x", "snippet": "a longer snippet"}]
    merged = web.merge([ddg, bing], 10)
    assert [r["title"] for r in merged] == ["B", "A", "C", "P"]
    assert merged[0]["snippet"] == "a longer snippet"


def test_merge_keeps_two_pages_per_site_unless_a_site_search():
    same = [[{"title": str(i), "url": f"https://one.test/{i}", "snippet": ""} for i in range(5)]]
    assert len(web.merge(same, 10)) == 2
    assert len(web.merge(same, 10, per_site=0)) == 5


def test_reads_top_pages_and_keeps_snippets_when_a_page_fails():
    results = [{"title": "Ok", "url": "https://ok.test", "snippet": "snip"},
               {"title": "Bad", "url": "https://bad.test", "snippet": "keep me"},
               {"title": "Vid", "url": "https://www.youtube.com/watch?v=abcdefghijk", "snippet": "video"}]

    async def fetch(url):
        if "bad" in url:
            raise RuntimeError("blocked")
        return {"text": "Menu\nThe Tata Motors chief executive officer is named here with the date he took over in 2024.\nFooter"}
    out = asyncio.run(live_search.read_top(results, "who is the ceo of tata motors", 3, 400, fetch=fetch))
    assert "From the page: The Tata Motors chief executive" in out[0]["snippet"]
    assert out[1]["snippet"] == "keep me" and out[2]["snippet"] == "video"


def test_videos_for_how_tos_but_not_code_or_prices():
    assert search_modes.wants_videos("how to make paneer butter masala")
    assert search_modes.wants_videos("yoga for back pain")
    assert search_modes.wants_videos("play some arijit singh songs")
    assert not search_modes.wants_videos("how to fix TypeError in python")
    assert not search_modes.wants_videos("how to say thank you in tamil")
    assert not search_modes.wants_videos("what is the price of gold")


def test_video_results_are_deduped_checked_and_ranked(monkeypatch):
    async def fake_search(query, limit):
        assert query.endswith("site:youtube.com")
        return [{"title": "Cat compilation - YouTube", "url": "https://www.youtube.com/watch?v=AAAAAAAAAAA"},
                {"title": "Paneer butter masala short", "url": "https://www.youtube.com/shorts/BBBBBBBBBBB"},
                {"title": "Paneer Butter Masala recipe - YouTube", "url": "https://youtu.be/CCCCCCCCCCC"},
                {"title": "Paneer Butter Masala again", "url": "https://www.youtube.com/watch?v=CCCCCCCCCCC&t=3"},
                {"title": "Gone paneer butter masala", "url": "https://www.youtube.com/watch?v=DDDDDDDDDDD"},
                {"title": "Channel", "url": "https://www.youtube.com/@chef"}]

    async def fake_oembed(client, vid):
        return None if vid == "DDDDDDDDDDD" else {"title": "", "channel": "Chef " + vid[0]}
    monkeypatch.setattr(search_modes.web, "search", fake_search)
    monkeypatch.setattr(search_modes, "_oembed", fake_oembed)
    out = asyncio.run(search_modes.video("paneer butter masala", 4))
    assert [v["url"][-11:] for v in out] == ["CCCCCCCCCCC", "BBBBBBBBBBB", "AAAAAAAAAAA"]
    assert out[0]["title"] == "Paneer Butter Masala recipe" and out[0]["channel"] == "Chef C"
    assert out[0]["thumbnail"] == "https://i.ytimg.com/vi/CCCCCCCCCCC/hqdefault.jpg"


def test_videos_row_without_web_search(monkeypatch):
    async def fake_video(query, limit):
        return [{"title": "T", "url": "https://www.youtube.com/watch?v=CCCCCCCCCCC",
                 "thumbnail": "https://i.ytimg.com/vi/CCCCCCCCCCC/hqdefault.jpg", "channel": "Chef"}]
    monkeypatch.setattr(search_modes, "video", fake_video)
    found = asyncio.run(live_search.gather(["how to make paneer butter masala"], search=False, videos=True))
    assert found["sources"] == [{"type": "clip", "title": "T", "url": "https://www.youtube.com/watch?v=CCCCCCCCCCC",
                                 "thumbnail": "https://i.ytimg.com/vi/CCCCCCCCCCC/hqdefault.jpg",
                                 "domain": "youtube.com", "channel": "Chef"}]


def test_deep_research_needs_asking_but_web_search_does_not():
    names = {t["function"]["name"] for t in default_registry().schemas(ToolContext(db=None, user_id="u", research=False))}
    assert "web_search" in names and "deep_research" not in names
