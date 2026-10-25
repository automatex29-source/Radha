"""Plugins: extra skills a user switches on or off in Settings > Plugins.

Always search the web (every answer checks the web first), Weather, Panchang & festivals, Cricket scores and the
Video maker. The Daily Gita verse is a plugin too, but it lives on each device (daily_verse.py), so the app shows
its switch and this module only lists it. Choices are stored on the user as `plugins: {id: bool}`; a plugin the
user never touched uses its default. Tools of a plugin that's off are hidden from Krish (Tool.plugin).
"""
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import limits
import media
import panchang
from agent import web
from agent.tools import Tool, ToolContext, ToolOutput, ToolRegistry
from auth import get_user_id_from_request

logger = logging.getLogger("radha.plugins")
db = None

PLUGINS = {
    "auto_search": {"name": "Always search the web", "plan": "basic", "default": False,
                    "blurb": "Krish checks the web before every answer, with sources",
                    "does": ["Fresh facts and news in every answer", "Sources you can tap to check",
                             "Answers can take a few seconds longer"]},
    "daily_verse": {"name": "Daily Gita verse", "plan": "basic", "default": False, "device": True,
                    "blurb": "A verse and its meaning every morning at 7",
                    "does": ["A notification on this device every morning", "One short verse with its meaning",
                             "Turn it on on each phone or computer you use"]},
    "weather": {"name": "Weather", "plan": "basic", "default": True,
                "blurb": "Today's weather and the week ahead for any city",
                "does": ["Temperature, rain chance and wind", "A 7-day forecast", "Sunrise and sunset times"]},
    "panchang": {"name": "Panchang & festivals", "plan": "basic", "default": True,
                 "blurb": "Tithi, nakshatra, muhurat timing and festival dates",
                 "does": ["Today's tithi, nakshatra, yoga and karana", "Upcoming festivals and fasting days",
                          "Worked out for your city's sunrise"]},
    "cricket": {"name": "Cricket scores", "plan": "basic", "default": True,
                "blurb": "Live scores and results of today's matches",
                "does": ["Live scores while matches are on", "Results and who won", "Upcoming matches"]},
    "video": {"name": "Video maker", "plan": "pro", "default": True,
              "blurb": "Short videos and reels from a description",
              "does": ["Ads, reels, trailers and stories", "Several scenes with captions", "Uses credits for each second"]},
}


def init(database):
    global db
    db = database


def ready(pid: str) -> bool:
    if pid == "video":
        return media.video_enabled()
    return True


def _plan_ok(plan: str, needed: str) -> bool:
    return limits.ORDER.index(plan) >= limits.ORDER.index(needed)


async def state(user_id: str) -> dict:
    """{plugin id: on} for this user, with defaults, ready and plan applied."""
    user = (await db.users.find_one({"id": user_id}, {"plugins": 1, "plan": 1, "planExpiresAt": 1}) or {}) \
        if db is not None and user_id else {}
    chosen = user.get("plugins") or {}
    plan = limits.plan_from(user) if user else "basic"
    return {pid: bool(chosen.get(pid, p["default"])) and ready(pid) and _plan_ok(plan, p["plan"])
            for pid, p in PLUGINS.items()}


async def turned_off(user_id: str) -> frozenset:
    return frozenset(pid for pid, on in (await state(user_id)).items() if not on)


async def listing(user_id: str) -> list:
    user = await db.users.find_one({"id": user_id}, {"plugins": 1, "plan": 1, "planExpiresAt": 1}) or {}
    plan = limits.plan_from(user)
    on = await state(user_id)
    return [{"id": pid, "name": p["name"], "blurb": p["blurb"], "does": p["does"], "plan": p["plan"],
             "on": on[pid], "ready": ready(pid), "locked": not _plan_ok(plan, p["plan"]), "device": p.get("device", False)}
            for pid, p in PLUGINS.items()]


# -------------------------------------------------------------------- tools
_WMO = {0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "fog", 48: "fog", 51: "light drizzle",
        53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
        67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers",
        81: "showers", 82: "heavy showers", 85: "snow showers", 86: "snow showers", 95: "thunderstorm",
        96: "thunderstorm with hail", 99: "thunderstorm with hail"}


async def geocode(city: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://geocoding-api.open-meteo.com/v1/search",
                             params={"name": city, "count": 1, "language": "en", "format": "json"})
    hits = r.json().get("results") if r.status_code == 200 else None
    return hits[0] if hits else None


def _place(hit: dict) -> str:
    return ", ".join(x for x in (hit.get("name"), hit.get("admin1"), hit.get("country")) if x)


async def _weather(ctx: ToolContext, args: dict) -> ToolOutput:
    city = (args.get("city") or "").strip()
    if not city:
        raise ValueError("'city' is required")
    hit = await geocode(city)
    if not hit:
        return ToolOutput(content=f"Couldn't find a place called {city}.", summary="Place not found", ok=False)
    days = max(1, min(int(args.get("days") or 3), 7))
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": hit["latitude"], "longitude": hit["longitude"], "timezone": "auto", "forecast_days": days,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset,uv_index_max"})
    r.raise_for_status()
    body = r.json()
    cur, d = body.get("current", {}), body.get("daily", {})
    lines = [f"Weather in {_place(hit)} (local time {cur.get('time', '').replace('T', ' ')}):",
             f"Now: {cur.get('temperature_2m')}°C, feels like {cur.get('apparent_temperature')}°C, "
             f"{_WMO.get(cur.get('weather_code'), 'mixed')}, humidity {cur.get('relative_humidity_2m')}%, "
             f"wind {cur.get('wind_speed_10m')} km/h."]
    for i, day in enumerate(d.get("time", [])):
        lines.append(f"- {day}: {_WMO.get(d['weather_code'][i], 'mixed')}, {d['temperature_2m_min'][i]}–"
                     f"{d['temperature_2m_max'][i]}°C, rain chance {d['precipitation_probability_max'][i]}%, "
                     f"UV {d['uv_index_max'][i]}, sunrise {d['sunrise'][i][-5:]}, sunset {d['sunset'][i][-5:]}")
    return ToolOutput(content="\n".join(lines) + "\nSource: Open-Meteo.", summary=f"{_place(hit)}: {cur.get('temperature_2m')}°C")


async def _panchang(ctx: ToolContext, args: dict) -> ToolOutput:
    lat, lon, tz, place = 28.6139, 77.2090, ZoneInfo("Asia/Kolkata"), "New Delhi"
    city = (args.get("city") or "").strip()
    if city:
        hit = await geocode(city)
        if hit:
            lat, lon, place = hit["latitude"], hit["longitude"], _place(hit)
            try:
                tz = ZoneInfo(hit.get("timezone") or "Asia/Kolkata")
            except ZoneInfoNotFoundError:
                pass
    try:
        day = date.fromisoformat(str(args.get("date"))[:10]) if args.get("date") else datetime.now(tz).date()
    except ValueError:
        raise ValueError("'date' must be YYYY-MM-DD")
    p = panchang.day_panchang(day, lat, lon, tz)
    lines = [f"Panchang for {day.strftime('%A, %d %B %Y')} at {place} (sunrise {p['sunrise']}):",
             f"- Vara: {p['vara']}", f"- Tithi: {p['tithi']} until {p['tithiEnds']}", f"- Paksha: {p['paksha']}",
             f"- Nakshatra: {p['nakshatra']} until {p['nakshatraEnds']}", f"- Yoga: {p['yoga']}",
             f"- Karana: {p['karana']}", f"- Lunar month: {p['month']}",
             f"- Sun in {p['sunSign']}, Moon in {p['moonSign']} (sidereal)"]
    if p["festivals"]:
        lines.append(f"- Today: {', '.join(p['festivals'])}")
    span = max(0, min(int(args.get("festival_days") or 30), 120))
    upcoming = []
    for i in range(1, span + 1):
        d = day + timedelta(days=i)
        for name in panchang.festivals_on(d, lat, lon):
            if not any(k in name for k in ("Purnima (full", "Amavasya (new", "Sankashti")):
                upcoming.append(f"- {d.strftime('%a %d %b %Y')}: {name}")
    if upcoming:
        lines.append(f"Festivals and fasting days in the next {span} days:")
        lines += upcoming
    lines.append("Worked out from the Sun and Moon (Lahiri ayanamsa, amanta months); regional calendars can differ "
                 "by a day, so say so when the exact day matters.")
    return ToolOutput(content="\n".join(lines), summary=f"{p['tithi']}, {p['nakshatra']}")


async def _cricket(ctx: ToolContext, args: dict) -> ToolOutput:
    key = os.environ.get("CRICAPI_KEY", "").strip()
    team = (args.get("team") or "").strip().lower()
    if key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get("https://api.cricapi.com/v1/currentMatches", params={"apikey": key, "offset": 0})
            matches = r.json().get("data") or [] if r.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            matches = []
        if team:
            matches = [m for m in matches if team in (m.get("name") or "").lower()]
        if matches:
            lines = []
            for m in matches[:12]:
                score = "; ".join(f"{s.get('inning', '')}: {s.get('r')}/{s.get('w')} ({s.get('o')} ov)" for s in m.get("score") or [])
                lines.append(f"- {m.get('name')} ({m.get('matchType', '').upper()}, {m.get('venue', '')}): "
                             f"{score or 'not started'}. {m.get('status', '')}")
            return ToolOutput(content="Cricket right now (CricAPI):\n" + "\n".join(lines), summary=f"{len(matches)} matches")
    query = f"{team + ' ' if team else ''}live cricket score today"
    results = await web.search(query, 6)
    if not results:
        return ToolOutput(content="Couldn't get cricket scores right now.", summary="No scores", ok=False)
    lines = [f"- {r['title']}: {r.get('snippet', '')} ({r['url']})" for r in results]
    return ToolOutput(content=f"Search results for '{query}' (check the newest; scores change fast):\n" + "\n".join(lines),
                      summary="Searched live scores")


def register_tools(registry: ToolRegistry):
    registry.register(Tool(
        "get_weather", "Current weather and the forecast (up to 7 days) for a city, with rain chance, UV, sunrise and "
        "sunset. Use it for any weather, rain or temperature question.",
        {"type": "object", "properties": {"city": {"type": "string"}, "days": {"type": "integer"}}, "required": ["city"]},
        _weather, label="Check weather", plugin="weather"))
    registry.register(Tool(
        "get_panchang", "Hindu panchang for a date and city: tithi, paksha, nakshatra, yoga, karana, lunar month, "
        "with end times, plus festivals and Ekadashi days in the next 'festival_days' days. Use it for questions about "
        "tithi, muhurat, festivals, vrat or when a festival is.",
        {"type": "object", "properties": {"date": {"type": "string", "description": "YYYY-MM-DD, default today"},
                                          "city": {"type": "string", "description": "Default New Delhi"},
                                          "festival_days": {"type": "integer", "description": "0-120, default 30"}}},
        _panchang, label="Check panchang", plugin="panchang"))
    registry.register(Tool(
        "cricket_scores", "Live cricket scores, results and today's matches. 'team' narrows it, e.g. India.",
        {"type": "object", "properties": {"team": {"type": "string"}}},
        _cricket, label="Cricket scores", plugin="cricket"))


# ------------------------------------------------------------------- routes
async def current_user_id(request: Request) -> str:
    return get_user_id_from_request(request)


class PluginIn(BaseModel):
    on: bool


router = APIRouter(prefix="/api/plugins")


@router.get("")
async def list_plugins(user_id: str = Depends(current_user_id)):
    return {"plugins": await listing(user_id)}


@router.put("/{pid}")
async def set_plugin(pid: str, body: PluginIn, user_id: str = Depends(current_user_id)):
    if pid not in PLUGINS:
        raise HTTPException(status_code=404, detail="That plugin isn't available.")
    user = await db.users.find_one({"id": user_id}, {"plan": 1, "planExpiresAt": 1})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    p = PLUGINS[pid]
    if body.on and not ready(pid):
        raise HTTPException(status_code=400, detail=f"{p['name']} is coming soon.")
    if body.on and not _plan_ok(limits.plan_from(user), p["plan"]):
        raise HTTPException(status_code=402, detail=f"{p['name']} is part of the {limits.PLANS[p['plan']]['name']} plan. "
                                                    "Upgrade to turn it on.")
    await db.users.update_one({"id": user_id}, {"$set": {f"plugins.{pid}": body.on}})
    return {"plugins": await listing(user_id)}
