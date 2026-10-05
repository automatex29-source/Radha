"""Live answer cards, like Perplexity's: weather (Open-Meteo) and stock prices (Yahoo Finance charts).

Both free with no key. Each returns (context for the model, card for the chat) or None.
"""
import logging
import re
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(6.0, connect=4.0)
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}

# ------------------------------------------------------------------- weather
_WEATHER = re.compile(r"\b(weather|temperature|forecast|raining|rain|humid|humidity|mausam|मौसम|तापमान)\b", re.I)
_PLACE_AFTER = re.compile(r"\b(?:in|at|of|for|near|mein|में)\s+([^\d?.,!]{2,40}?)(?:\s+(?:today|tomorrow|now|this week|right now|aaj|kal)\b|[?.,!]|$)", re.I)
_FILLER = re.compile(r"\b(what|what's|whats|is|the|weather|temperature|forecast|today|tomorrow|now|right|current|"
                     r"like|how|tell|me|will|it|rain|raining|in|at|of|for|kya|hai|hoga|aaj|kal|ka|ki|ke|mausam|"
                     r"this|week|please|humidity|humid)\b", re.I)

WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Cloudy", 45: "Fog", 48: "Fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Rain showers", 82: "Heavy showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}


def weather_place(text: str) -> str:
    if not _WEATHER.search(text or ""):
        return ""
    m = _PLACE_AFTER.search(text)
    place = m.group(1) if m else _FILLER.sub(" ", text)
    place = re.sub(r"[^\w\s.'-]", " ", place)
    place = " ".join(_FILLER.sub(" ", place).split())
    return place[:40] if len(place) >= 2 else ""


async def weather(text: str) -> Optional[Tuple[str, dict]]:
    place = weather_place(text)
    if not place:
        return None
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA) as client:
        geo = (await client.get("https://geocoding-api.open-meteo.com/v1/search",
                                params={"name": place, "count": 1, "language": "en"})).json()
        hits = geo.get("results") or []
        if not hits:
            return None
        g = hits[0]
        data = (await client.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto", "forecast_days": 5,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})).json()
    return weather_card(g, data)


def weather_card(g: dict, data: dict) -> Optional[Tuple[str, dict]]:
    cur, daily = data.get("current") or {}, data.get("daily") or {}
    if "temperature_2m" not in cur:
        return None
    name = ", ".join(x for x in [g.get("name"), g.get("admin1"), g.get("country")] if x)
    days = [{"date": d, "code": c, "label": WEATHER_CODES.get(c, ""), "max": round(hi), "min": round(lo), "rain": r}
            for d, c, hi, lo, r in zip(daily.get("time", []), daily.get("weather_code", []),
                                       daily.get("temperature_2m_max", []), daily.get("temperature_2m_min", []),
                                       daily.get("precipitation_probability_max", []))]
    card = {"type": "weather", "place": name, "temp": round(cur["temperature_2m"]),
            "feels": round(cur.get("apparent_temperature", cur["temperature_2m"])),
            "humidity": cur.get("relative_humidity_2m"), "wind": cur.get("wind_speed_10m"),
            "code": cur.get("weather_code"), "label": WEATHER_CODES.get(cur.get("weather_code"), ""),
            "days": days, "url": "https://open-meteo.com/"}
    forecast = "; ".join(f"{d['date']}: {d['label']}, {d['min']}-{d['max']}°C, rain chance {d['rain']}%" for d in days)
    context = (f"Live weather for {name} (Open-Meteo): now {card['temp']}°C (feels {card['feels']}°C), {card['label']}, "
               f"humidity {card['humidity']}%, wind {card['wind']} km/h. Next days: {forecast}. "
               "The app shows this as a weather card, so answer in one or two sentences.")
    return context, card


# -------------------------------------------------------------------- stocks
_STOCK = re.compile(r"\b(share price|stock price|stock|shares|nse|bse|sensex|nifty|market cap|ticker)\b", re.I)
_STOCK_FILLER = re.compile(r"\b(what|what's|whats|is|the|of|today|now|current|price|share|shares|stock|stocks|"
                           r"live|nse|bse|kya|hai|ka|ki|aaj|rate|value|how|much|tell|me|about|latest|market|cap|news|update|updates|"
                           r"should|i|buy|sell|invest|in|analysis|performance|trend|week|month|year|and|vs|do|does|"
                           r"did|go|up|down|why|ticker|a|an|my|good|bad)\b", re.I)
_INDEXES = {"sensex": ("^BSESN", "BSE Sensex"), "nifty": ("^NSEI", "Nifty 50"), "bank nifty": ("^NSEBANK", "Nifty Bank")}


def stock_query(text: str) -> str:
    if not _STOCK.search(text or ""):
        return ""
    q = " ".join(_STOCK_FILLER.sub(" ", re.sub(r"[^\w\s&.-]", " ", text)).split())
    return q[:50]


async def stock(text: str) -> Optional[Tuple[str, dict]]:
    low = (text or "").lower()
    index = next((v for k, v in sorted(_INDEXES.items(), key=lambda kv: -len(kv[0])) if k in low), None)
    query = "" if index else stock_query(text)
    if not index and len(query) < 2:
        return None
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA, follow_redirects=True) as client:
        if index:
            symbol = index[0]
        else:
            found = (await client.get("https://query2.finance.yahoo.com/v1/finance/search",
                                      params={"q": query, "quotesCount": 6, "newsCount": 0})).json()
            symbol = pick_symbol(found.get("quotes") or [])
            if not symbol:
                return None
        chart = (await client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                                  params={"range": "1mo", "interval": "1d"})).json()
    return stock_card(chart, index[1] if index else "")


def pick_symbol(quotes: list) -> str:
    equities = [q for q in quotes if q.get("quoteType") in ("EQUITY", "ETF", "INDEX") and q.get("symbol")]
    for suffix in (".NS", ".BO"):  # Indian listings first
        for q in equities:
            if q["symbol"].endswith(suffix):
                return q["symbol"]
    return equities[0]["symbol"] if equities else ""


def stock_card(chart: dict, name: str = "") -> Optional[Tuple[str, dict]]:
    res = ((chart.get("chart") or {}).get("result") or [None])[0]
    if not res:
        return None
    meta = res.get("meta") or {}
    price = meta.get("regularMarketPrice")
    closes = [c for c in (((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []) if c is not None]
    if price is None:
        return None
    prev = meta.get("previousClose") or meta.get("chartPreviousClose") or (closes[-2] if len(closes) > 1 else price)
    change = price - prev
    symbol = meta.get("symbol", "")
    card = {"type": "stock", "name": name or meta.get("longName") or meta.get("shortName") or symbol, "symbol": symbol,
            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName") or "", "currency": meta.get("currency", ""),
            "price": round(price, 2), "change": round(change, 2), "changePct": round(change / prev * 100, 2) if prev else 0,
            "points": [round(c, 2) for c in closes[-30:]], "url": f"https://finance.yahoo.com/quote/{symbol}"}
    month = f" One month ago: {card['points'][0]}." if card["points"] else ""
    context = (f"Live market data (Yahoo Finance): {card['name']} ({symbol}, {card['exchange']}) is at {card['price']} "
               f"{card['currency']}, {card['change']:+} ({card['changePct']:+}%) today.{month} The app shows this as a "
               "price card with a chart. Prices can be delayed; don't give buy or sell advice.")
    return context, card
