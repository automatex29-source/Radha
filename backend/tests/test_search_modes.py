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


import widgets


def test_weather_place():
    assert widgets.weather_place("weather in New Delhi today") == "New Delhi"
    assert widgets.weather_place("mumbai weather") == "mumbai"
    assert widgets.weather_place("will it rain in Pune tomorrow?") == "Pune"
    assert widgets.weather_place("write a poem") == ""


def test_weather_card():
    g = {"name": "Pune", "admin1": "Maharashtra", "country": "India"}
    data = {"current": {"temperature_2m": 27.6, "apparent_temperature": 30.1, "relative_humidity_2m": 70,
                        "wind_speed_10m": 9.4, "weather_code": 2},
            "daily": {"time": ["2026-10-05"], "weather_code": [61], "temperature_2m_max": [29.2],
                      "temperature_2m_min": [21.4], "precipitation_probability_max": [60]}}
    context, card = widgets.weather_card(g, data)
    assert card["place"] == "Pune, Maharashtra, India" and card["temp"] == 28 and card["label"] == "Partly cloudy"
    assert card["days"] == [{"date": "2026-10-05", "code": 61, "label": "Light rain", "max": 29, "min": 21, "rain": 60}]
    assert "28°C" in context


def test_stock_query_and_symbol():
    assert widgets.stock_query("tata motors share price today") == "tata motors"
    assert widgets.stock_query("should I buy reliance shares?") == "reliance"
    assert widgets.stock_query("can you share a poem") == ""
    quotes = [{"symbol": "TTM", "quoteType": "EQUITY"}, {"symbol": "TATAMOTORS.NS", "quoteType": "EQUITY"}]
    assert widgets.pick_symbol(quotes) == "TATAMOTORS.NS"


def test_stock_card():
    chart = {"chart": {"result": [{"meta": {"symbol": "TATAMOTORS.NS", "longName": "Tata Motors Limited",
                                            "regularMarketPrice": 1020.5, "previousClose": 1000.0, "currency": "INR",
                                            "fullExchangeName": "NSE"},
                                   "indicators": {"quote": [{"close": [990.0, None, 1000.0, 1020.5]}]}}]}}
    context, card = widgets.stock_card(chart)
    assert card["changePct"] == 2.05 and card["points"] == [990.0, 1000.0, 1020.5] and card["currency"] == "INR"
    assert "Tata Motors Limited" in context


def test_agent_asks_again_when_tools_end_in_silence():
    from agent import runtime
    from agent.tools import ToolContext

    calls = []

    async def stream_fn(model, messages, tools):
        calls.append([m.get("content") for m in messages])
        if len(calls) == 1:
            yield {"type": "tool_calls", "calls": [{"id": "1", "name": "web_search", "arguments": '{"query": "x"}'}]}
        elif len(calls) == 2:
            return  # the silent ending some models produce
        else:
            yield {"type": "text", "text": "Will Cathcart runs WhatsApp."}

    class Registry:
        def schemas(self, ctx):
            return [{}]

        def active(self, ctx):
            return []

        async def run(self, name, args, ctx):
            from types import SimpleNamespace
            return SimpleNamespace(ok=True, summary="ok", content="results", media=[])

    async def go():
        return [ev async for ev in runtime.run_agent(stream_fn, Registry(), ToolContext(db=None, user_id="u"), "m",
                                                     [{"role": "user", "content": "who runs whatsapp"}])]
    events = asyncio.run(go())
    assert any(e.get("text") == "Will Cathcart runs WhatsApp." for e in events)
    assert calls[-1][-1] == runtime.ANSWER_NUDGE


def test_pro_search_leads_with_planned_queries(monkeypatch):
    from agent import research

    async def fake_plan(question, focus, model, ask):
        return [question, "WhatsApp CEO 2026", "head of WhatsApp Meta"]

    seen = {}

    async def fake_gather(queries, terms, max_sources, max_chars, **limits):
        seen["limits"] = limits
        seen["queries"] = queries
        return []
    monkeypatch.setattr(research, "plan", fake_plan)
    monkeypatch.setattr(research, "gather_sources", fake_gather)
    asyncio.run(search_modes.pro("who isceo of whasapp", "m"))
    assert seen["queries"] == ["WhatsApp CEO 2026", "head of WhatsApp Meta", "who isceo of whasapp"]
    assert seen["limits"] == {"search_timeout": 12, "fetch_timeout": 8}


def test_pro_falls_back_to_plain_search_when_it_finds_nothing(monkeypatch):
    async def empty_pro(question, model, **k):
        return {"queries": ["Bharti Airtel CEO", "who is ceo of BHARTI Airtel"], "results": []}
    seen = []

    async def fake_search(query, focus, limit):
        seen.append(query)
        return [{"title": "Airtel leadership", "url": "https://airtel.in/leadership", "snippet": "Gopal Vittal"}]
    monkeypatch.setattr(search_modes, "pro", empty_pro)
    monkeypatch.setattr(search_modes, "search", fake_search)
    found = asyncio.run(live_search.gather(["who is the ceo of BHARTI Airtel"], pro=True, model="m"))
    assert seen == ["Bharti Airtel CEO"] and found["queries"] == ["Bharti Airtel CEO"]
    assert found["sources"][0]["url"] == "https://airtel.in/leadership" and "Gopal Vittal" in found["context"]


def test_pro_falls_back_when_it_times_out(monkeypatch):
    async def slow_pro(question, model, **k):
        await asyncio.sleep(5)

    async def fake_search(query, focus, limit):
        return [{"title": "Airtel", "url": "https://airtel.in/", "snippet": "CEO"}]
    monkeypatch.setattr(live_search, "PRO_TIMEOUT", 8.2)
    monkeypatch.setattr(live_search, "LOOKUP_TIMEOUT", 6.0)
    monkeypatch.setattr(search_modes, "pro", slow_pro)
    monkeypatch.setattr(search_modes, "search", fake_search)
    found = asyncio.run(live_search.gather(["ceo of airtel"], pro=True, model="m"))
    assert found["sources"][0]["url"] == "https://airtel.in/" and found["queries"] == ["ceo of airtel"]


def test_model_web_search_adds_numbered_cards_and_stops_after_limit(monkeypatch):
    from agent import tools, web as agent_web

    async def fake_search(query, limit=6):
        return [{"title": "Old", "url": "https://a.test/old", "snippet": "x"},
                {"title": "Airtel CEO", "url": "https://www.airtel.in/ceo", "snippet": "Shashwat Sharma"}]
    monkeypatch.setattr(agent_web, "search", fake_search)
    sources = [{"type": "weather"}, {"type": "web", "url": "https://a.test/old", "title": "Old", "domain": "a.test"}]
    ctx = tools.ToolContext(db=None, user_id="u", sources=sources, searches_left=1)
    out = asyncio.run(tools._web_search(ctx, {"query": "airtel ceo"}))
    assert "[1] Old" in out.content and "[2] Airtel CEO" in out.content
    assert sources[-1] == {"type": "web", "title": "Airtel CEO", "url": "https://www.airtel.in/ceo",
                           "domain": "airtel.in", "snippet": "Shashwat Sharma"} and len(sources) == 3
    again = asyncio.run(tools._web_search(ctx, {"query": "airtel ceo 2026"}))
    assert again.content == tools.SEARCH_DONE and len(sources) == 3


def test_pro_drops_off_topic_pages():
    pages = [{"title": "Current | Future of Banking", "url": "https://current.com/", "text": "Banking app"},
             {"title": "Airtel leadership", "url": "https://airtel.in/about", "text": "CEO Shashwat Sharma"},
             {"title": "Bharti Airtel", "url": "https://en.wikipedia.org/wiki/Bharti_Airtel", "text": "The CEO is"}]
    kept = search_modes.on_topic(pages, research_terms("WHO IS THE CEO OF AIRTEL"))
    assert [p["url"] for p in kept] == ["https://airtel.in/about", "https://en.wikipedia.org/wiki/Bharti_Airtel"]
    assert search_modes.on_topic(pages[:1], ["airtel"]) == pages[:1]  # nothing matches: keep what there is


def research_terms(text):
    from agent import research
    return research.keywords(text)


def test_no_pictures_for_who_holds_a_job():
    assert not search_modes.wants_images("WHO IS THE CEO OF AIRTEL")
    assert search_modes.wants_images("who is virat kohli")


def test_groq_gets_a_smaller_pro_pack(monkeypatch):
    seen = {}

    async def fake_pro(question, model, **size):
        seen.update(size)
        return {"queries": [question], "results": [{"title": "A", "url": "https://a.test", "snippet": "s"}]}
    monkeypatch.setattr(search_modes, "pro", fake_pro)
    asyncio.run(live_search.gather(["airtel ceo"], pro=True, model="openai/gpt-oss-120b"))
    assert seen == {"max_sources": 4, "max_chars": 500}
