"""Live web lookups for chat.

Krish searches on its own when a question needs fresh or checkable facts (see auto_search), so the user doesn't
have to turn on the Web button or ask for it. The Web button (or asking in words, "search the web for...")
always searches, with more results and pictures. Quick live cards (exchange rates, weather, stocks) run either way.
"""
import asyncio
import datetime
import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import search_modes
import widgets
from agent import llm as agent_llm, research, web

logger = logging.getLogger(__name__)

LOOKUP_TIMEOUT = 6.0

_CURRENT = re.compile(
    r"\b(today|todays|tonight|right now|current(ly)?|latest|recent(ly)?|this (week|month|year)|yesterday|"
    r"news|headlines?|price|prices|rate|rates|weather|forecast|temperature|score|scores|"
    r"stock|share price|sensex|nifty|bitcoin|btc|crypto|gold|silver|petrol|diesel|election|"
    r"search|google|look ?up|browse|internet|who won|who is the|20[2-9]\d)\b",
    re.I,
)
# Fact questions ("who is", "how much", "best phones under 20000", "X vs Y") also get a search, like Perplexity.
_QUESTION = re.compile(
    r"^\s*(who|what|when|where|which|whose|how (much|many|old|far|long|big|tall)|is there|are there|did|does|"
    r"kaun|kya|kab|kahan|kitna|kitne)\b|\b(best|top \d+|vs\.?|versus|compare|comparison|review|reviews|"
    r"near me|cheapest|release date|launch(ed)?|founder|ceo|population|capital of|net worth|salary|"
    r"how to (buy|apply|get|book|register|download))\b",
    re.I,
)
_CURRENCY = web.CURRENCY
CITE_NOTE = (
    "These results were searched just now for this question: answer from them directly and don't call "
    "web_search again unless they clearly don't contain the answer. If the question has a typo, answer what "
    "the user meant. "
    "Write a full answer, not one line: open with the direct answer in a sentence or two, then give the useful "
    "details (who, what, when, key numbers, what changed recently) in short paragraphs or bullets with bold "
    "key facts. When results show a change over time (someone appointed, a price revised), say what is true as of "
    "today's date and when it changed; a change that a result says takes effect on a date already passed has "
    "happened, so the newer person or number is current. "
    "Cite: after each sentence that uses a numbered web result, add its number in square brackets, like [1] or "
    "[2][3]. Use only the numbers listed here. Don't add a separate list of sources or links; the app shows them. "
    "If the results don't relate to what the user asked (a story, a poem, code, a chat), ignore them and answer "
    "normally, without citations. Facts about Krish AI and EmpireX come from your instructions, never from these "
    "results: other companies share the EmpireX name."
)


# Fast phone typing ("plzzz tell weathr tmrw") made searches miss and kept the checks below from noticing a
# question. Only short forms that can't mean anything else are expanded; the model still reads the raw message.
_SHORT_FORMS = {
    "pls": "please", "plz": "please", "plss": "please", "plzz": "please", "tmrw": "tomorrow", "tmr": "tomorrow",
    "tmrow": "tomorrow", "tomoro": "tomorrow", "tommorow": "tomorrow", "tomorow": "tomorrow", "2day": "today",
    "tday": "today", "2moro": "tomorrow", "abt": "about", "wht": "what", "wat": "what", "whr": "where",
    "hw": "how", "bcz": "because", "bcoz": "because", "coz": "because", "cuz": "because", "ppl": "people",
    "msg": "message", "govt": "government", "info": "information", "latst": "latest", "lates": "latest",
    "weathr": "weather", "wheather": "weather", "temprature": "temperature", "tempreture": "temperature",
    "pric": "price", "prise": "price", "nws": "news", "srch": "search", "serch": "search", "seach": "search",
    "gogle": "google", "googel": "google", "rn": "right now", "yday": "yesterday", "yesterdy": "yesterday",
}
_WORD = re.compile(r"[A-Za-z0-9]+")
_STRETCHED = re.compile(r"([A-VX-Za-vx-z])\1{2,}")  # not w, so www. stays


def tidy(text: str) -> str:
    """The message with stretched letters ("pleaseeee") cut to two and common short forms spelled out, for
    searching and for spotting what kind of question it is."""
    if not text:
        return text
    text = _STRETCHED.sub(r"\1\1", text)
    text = _WORD.sub(lambda m: _SHORT_FORMS.get(m.group(0).lower(), m.group(0)), text)
    return re.sub(r"[ \t]{2,}", " ", text)


def _recent_user_text(user_messages: List[str]) -> str:
    """The latest question, joined with the one before it when it is a short follow-up like "USD"."""
    if not user_messages:
        return ""
    last = user_messages[-1].strip()
    # "weather in Mumbai" or "who is Sachin" is a new question of its own, not a follow-up.
    stands_alone = _QUESTION.search(last) or widgets.weather_place(last) or widgets.stock_query(last)
    if len(last.split()) <= 3 and len(user_messages) > 1 and not stands_alone:
        return f"{user_messages[-2].strip()} {last}"
    return last


def _with_weather_place(user_messages: List[str], text: str) -> str:
    """ "will it rain tomorrow" after "I'm in Gurugram" becomes "will it rain tomorrow in Gurugram", so the
    weather card (and the search) look up the right city instead of the model guessing."""
    if not widgets.is_weather(text) or widgets.weather_place(text):
        return text
    for earlier in reversed(user_messages[-7:-1]):
        place = widgets.weather_place(earlier) or (len(earlier.split()) <= 10 and widgets.named_place(earlier))
        if place:
            return f"{text.rstrip(' ?.!')} in {place}"
    return text


# Questions about Krish AI or EmpireX itself are answered from the system prompt: the web has other,
# unrelated companies called EmpireX, and their founders' names ended up in answers.
_ABOUT_US = re.compile(
    r"\b(krish ?ai|empire ?x|automatex)\b|\bwho (made|built|created|developed|owns|designed|trained) (you|krish)\b|"
    r"\byour (owner|owners|founder|founders|creator|creators|maker|makers|company|ceo|developer|developers)\b|"
    r"\b(who|which company) (is|are) (behind|your)\b|\b(tum|aap|tumhe|aapko|tujhe) ?(ko)? ?kisne\b",
    re.I,
)
# Greetings and thanks get a friendly reply, not search results.
_SMALL_TALK = re.compile(
    r"^\s*(hi+|hello+|hey+|hii+|namaste|namaskar|good (morning|afternoon|evening|night)|thanks?|thank you|thx|ty|"
    r"ok(ay)?|okk+|cool|nice|great|bye|good ?bye|yes|no|haan|ha|nahi|theek hai|thik hai|done|sure|hmm+)"
    r"[\s!.,?🙏😊👍]*(krish|bro|dear|ji)?[\s!.,?🙏😊👍]*$",
    re.I,
)
# The user asked for a search in words, so it runs even with the Web button off.
_ASKS_SEARCH = re.compile(
    r"\b(search|google|browse|web ?search|look (it |this |that )?up)\b|\b(on|from|in) the (web|internet|net)\b|"
    r"\b(internet|online|net) (pe|par|se)\b|\bsearch (karo|kar|kro)\b",
    re.I,
)
# Questions whose answer changes over time: with web search off, Krish suggests turning it on.
_FRESH = re.compile(
    r"\b(today|todays|tonight|right now|current(ly)?|latest|recent(ly)?|this (week|month|year)|yesterday|"
    r"news|headlines?|price|prices|rate|rates|score|scores|stock|share price|sensex|nifty|bitcoin|btc|"
    r"crypto|gold|silver|petrol|diesel|election|results?|weather|forecast|temperature|rain|raining|mausam|baarish|barish|who won|who is the|20[2-9]\d|best(?! (way|practices?|of luck))|top \d+|vs\.?|"
    r"versus|compare|cheapest|release date|launch(ed)?|ceo|founder|president|prime minister|net worth|"
    r"population|salary|near me|aaj|abhi|taaza|khabar)\b",
    re.I,
)
# A weather question with no live weather data must not get a made-up forecast ("zero chance of rain").
NO_WEATHER_NOTE = (
    "Live weather data for this place couldn't be loaded just now. Don't state a forecast, temperature or chance of "
    "rain from memory or guesswork. Use the web results above if they give a current forecast for this place, "
    "citing them; otherwise say plainly that you couldn't check the live weather right now. (If the message isn't "
    "asking about the weather, ignore this note.)"
)
ASK_PLACE_NOTE = (
    "This is a weather question but no city is named, so there is no live weather data. Don't guess a forecast, "
    "temperature or chance of rain: ask which city or area they mean, in one short sentence. (If the message "
    "isn't asking about the weather, ignore this note.)"
)
MAX_SEARCH_CHARS = 1500  # long pasted text (an essay, a log) isn't a search query


def needs_lookup(text: str) -> bool:
    """Every answer is backed by a web search, except greetings, questions about Krish/EmpireX itself, code and
    long pasted text (unless it asks about something current)."""
    if not text or _ABOUT_US.search(text) or _SMALL_TALK.match(text):
        return False
    if _CURRENT.search(text) or _CURRENCY.search(text):
        return True
    return len(text) <= MAX_SEARCH_CHARS and "```" not in text


def asks_for_search(text: str) -> bool:
    """True when the user asked in words for a web search."""
    return bool(text) and len(text) <= MAX_SEARCH_CHARS and bool(_ASKS_SEARCH.search(tidy(text)))


def suggests_web(text: str) -> bool:
    """True when the answer likely depends on fresh facts, so turning web search on would help."""
    if not text or len(text) > MAX_SEARCH_CHARS or "```" in text or _ABOUT_US.search(text) or _SMALL_TALK.match(text):
        return False
    text = tidy(text)
    if _MAKE.search(text) and not _NEWSY.search(text):  # "write a poem about rain" isn't about the weather
        return False
    return bool(_FRESH.search(text) or _CURRENCY.search(text))


# Asks for something to be made, not looked up: a poem, an email, code, a translation. Searching adds nothing.
_MAKE = re.compile(
    r"^\s*(please |pls |can you |could you |kindly )?(write|draft|compose|create|make|generate|design|draw|paint|"
    r"translate|summari[sz]e|rewrite|rephrase|paraphrase|proofread|correct|improve|fix|debug|convert|calculate|"
    r"solve|code|build|imagine|pretend|roleplay|act as|tell me a (joke|story)|likh|likho|banao|bana do)\b|"
    r"\b(poem|poetry|shayari|story|essay|joke|lyrics|cover letter|resume)\b",
    re.I,
)
# A specific thing named in the question (a person, place, product, company, number), which the web knows
# better than memory: "what is the Vande Bharat top speed", "kya hai iPhone 17 ka price".
_NAMED = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z]{2,}|\d")
# "what/why/how" alone is often timeless ("what is photosynthesis", "why is the sky blue"): search only when it
# names something specific or asks about something that changes.
_FACT = re.compile(
    r"^\s*(who|when|where|which|whose|how (much|many|old|far|long|big|tall|tall|fast)|is there|are there|"
    r"kaun|kab|kahan|kitna|kitne|kitni)\b|\b(best|top \d+|vs\.?|versus|compare|comparison|review|reviews|"
    r"near me|cheapest|release date|launch(ed)?|founder|ceo|population|capital of|net worth|salary|"
    r"how to (buy|apply|get|book|register|download|reach|contact)|fees?|admission|timings?|address|phone number|"
    r"official (site|website)|last date|eligibility|syllabus|exam date|helpline|customer care)\b",
    re.I,
)
_NEWSY = re.compile(r"\b(latest|today'?s?|news|headlines?|current|this week|recent|trending|best|top \d+|"
                    r"prices?)\b", re.I)
_WHAT = re.compile(r"^\s*(what|kya|tell me about|who is|info on|details of|information about)\b", re.I)


def auto_search(text: str) -> bool:
    """Krish's own judgment of whether a question needs the web: news, prices, scores, people, places, products,
    dates, rules and anything else that changes or is easy to get wrong from memory. Not for greetings, writing
    tasks, code, maths or timeless explanations, where a search only slows the answer down."""
    if not text or len(text) > MAX_SEARCH_CHARS or "```" in text or _ABOUT_US.search(text) or _SMALL_TALK.match(text):
        return False
    text = tidy(text).strip()
    if asks_for_search(text):
        return True
    if _MAKE.search(text):  # "write a poem about rain" isn't a weather question; "summarise today's news" needs news
        return bool(_NEWSY.search(text))
    if suggests_web(text):
        return True
    if len(text.split()) < 2:
        return False
    if _FACT.search(text):
        return True
    return bool(_WHAT.match(text) and _NAMED.search(text[1:]))


# Words that help a person read the message but only add noise to a search query.
_FILLER = re.compile(
    r"^\s*((hey|hi|hello|ok|okay|so|bro|dear|yaar|krish( ai)?|please|pls|plz|kindly|"
    r"can you|could you|would you|will you|tell me|let me know|i want to know|i wanna know|do you know|"
    r"search( the web| online| google)?( for)?|google|look up|find( me)?|show me|give me)[\s,!.:]+)+",
    re.I,
)
_TAIL = re.compile(r"(?:[\s,]+(?:please|pls|plz|bro|yaar|krish|batao|bata do|btao|bolo|na)\b|[\s,]*[?!.])+\s*$", re.I)
_TIMELY = re.compile(r"\b(latest|current(ly)?|this year|recent(ly)?|new|newest|upcoming|ranking|rankings|"
                     r"best|top \d+)\b", re.I)


def search_query(text: str, today: datetime.date = None) -> str:
    """The message as a search engine likes it: no greetings or "can you tell me", and with the year added to a
    question about the latest anything, so engines don't bring back pages from years ago."""
    q = _TAIL.sub("", _FILLER.sub("", tidy(text or "")).strip()).strip() or (text or "").strip()
    year = (today or datetime.date.today()).year
    if _TIMELY.search(q) and not re.search(r"\b(19|20)\d\d\b", q):
        q = f"{q} {year}"
    return q[:200]


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


async def _rates(text: str) -> Optional[str]:
    return await web.exchange_rates(text) or None


_HEADINGS = {"web": "Web search results", "academic": "Scholarly papers (OpenAlex)",
             "social": "Reddit discussions", "video": "YouTube videos"}
PRO_TIMEOUT = 35.0


def _format(results: List[dict], focus: str = "web") -> Optional[Tuple[str, List[dict]]]:
    results = [r for r in results if r.get("url", "").startswith("http")]
    if not results:
        return None
    lines = [f"[{i + 1}] {r['title']} ({r['url']})\n   {r['snippet']}" for i, r in enumerate(results)]
    cards = []
    for r in results:
        card = {"type": "video" if focus == "video" else "web", "title": r["title"] or domain_of(r["url"]),
                "url": r["url"], "domain": domain_of(r["url"]), "snippet": (r.get("snippet") or "")[:240]}
        if r.get("thumbnail"):
            card["thumbnail"] = r["thumbnail"]
        cards.append(card)
    return f"{_HEADINGS.get(focus, _HEADINGS['web'])}:\n" + "\n".join(lines) + "\n" + CITE_NOTE, cards


# The top results' pages are read for the passages that answer the question: a search snippet is a line or two,
# often cut mid-sentence, and answers built only on snippets missed the details.
READ_TIMEOUT = 3.5
_UNREADABLE = re.compile(r"\.pdf($|\?)|youtube\.com|youtu\.be|reddit\.com|facebook\.com|instagram\.com|x\.com|"
                         r"twitter\.com", re.I)


async def read_top(results: List[dict], question: str, pages: int, chars: int, fetch=None) -> List[dict]:
    """The results with the best passages from the first few pages added to their snippets. A page that is slow,
    blocked or off-topic keeps its snippet, so reading never loses a result."""
    fetch = fetch or web.fetch_page
    terms = set(research.keywords(question))

    async def one(r: dict) -> dict:
        if _UNREADABLE.search(r.get("url", "")):
            return r
        try:
            page = await asyncio.wait_for(fetch(r["url"]), READ_TIMEOUT)
        except Exception:
            return r
        passage = research.best_passages(page.get("text") or "", list(terms), chars).strip()
        if not passage or not terms & set(research.keywords(passage)):
            return r
        return {**r, "snippet": f"{(r.get('snippet') or '').strip()}\n   From the page: {' '.join(passage.split())}"}

    readable = [r for r in results if not _UNREADABLE.search(r.get("url", ""))][:pages]
    done = dict(zip((id(r) for r in readable), await asyncio.gather(*(one(r) for r in readable))))
    return [done.get(id(r), r) for r in results]


async def _search(text: str, limit: int = 5, focus: str = "web", model: str = "",
                  read: bool = True) -> Optional[Tuple[str, List[dict]]]:
    query = search_query(text) if focus == "web" else text[:200]
    results = await search_modes.search(query, focus, limit)
    if read and focus == "web" and results:
        # Groq's free tier fits about 8,000 tokens per request, so free models read fewer, shorter passages.
        pages, chars = (2, 350) if model and agent_llm.lean(model) else (3, 700)
        results = await read_top(results, text, pages, chars)
    return _format(results, focus)


# Hinglish or Hindi questions get Hindi videos first: "paneer kaise banaye" wants a Hindi recipe video.
_HINDI = re.compile(r"[\u0900-\u097F]|\b(kaise|kaisa|kya|hai|hain|banaye|banate|banaen|karein|karte|kare|sikhe|"
                    r"sikho|sikhna|mein|wala|wali|ghar|bina|ke liye)\b", re.I)
_HOW_FILLER = re.compile(r"^\s*(please |pls |can you |could you |show me |give me |suggest |recommend )*"
                         r"((a |some |any )?(youtube )?(videos?|tutorials?) (on|for|about|of) )?", re.I)


def video_query(text: str) -> str:
    """What to look for on YouTube: the question without "can you show me a video on", in Hindi when asked that way."""
    q = _TAIL.sub("", _HOW_FILLER.sub("", _FILLER.sub("", tidy(text or "")))).strip() or text.strip()
    q = re.sub(r"\b(on |from |in )?youtube\b", "", q, flags=re.I).strip()
    if _HINDI.search(text or "") and "hindi" not in q.lower():
        q += " in hindi"
    return q[:150]


async def _pro(text: str, model: str) -> Optional[Tuple[str, List[dict], List[str]]]:
    # Pro gets most of the time; if it finds nothing (slow engines, pages that won't load), a plain search
    # with the planner's cleaned-up query still brings back sources.
    try:
        # Groq's free tier fits about 8,000 tokens per request, so it gets a smaller reading pack.
        size = {"max_sources": 4, "max_chars": 500} if model and agent_llm.lean(model) else {}
        found = await asyncio.wait_for(search_modes.pro(text[:300], model, **size), PRO_TIMEOUT - LOOKUP_TIMEOUT - 2)
    except Exception as exc:
        logger.warning("Pro search failed, falling back to a plain search: %r", exc)
        found = {"queries": [], "results": []}
    formatted = _format(found["results"])
    if formatted:
        return (*formatted, found["queries"])
    query = (found["queries"] or [text])[0][:200]
    try:
        plain = await asyncio.wait_for(_search(query, 8, read=False), LOOKUP_TIMEOUT)
    except Exception as exc:
        logger.warning("Plain search after Pro failed: %r", exc)
        plain = None
    return (*plain, [query]) if plain else None


async def gather(user_messages: List[str], search: bool = True, force: bool = False, focus: str = "web",
                 pro: bool = False, model: str = "", videos: Optional[bool] = None) -> dict:
    """Live context for the latest question: {"context", "sources", "queries"}; context is None when the
    question needs no lookup or every lookup fails.

    force=True (the Search button) always searches, with more results and pictures; focus picks Academic,
    Social or Video sources; pro plans several searches and reads the best pages. With search=False only
    exchange rates are fetched. videos=True adds a row of YouTube videos (how-tos, recipes, lessons) even when
    the web isn't searched; by default only the Search button adds them.
    """
    empty = {"context": None, "sources": [], "queries": []}
    focus = focus if focus in search_modes.FOCUSES else "web"
    force = force or pro or focus != "web"
    text = tidy(_recent_user_text(user_messages))
    text = _with_weather_place(user_messages, text) if text else text
    if not text or not (force or needs_lookup(text)):
        return empty
    jobs = {}  # name -> awaitable; each part has its own time limit, so one slow source never costs the rest
    if _CURRENCY.search(text):
        jobs["rates"] = asyncio.wait_for(_rates(text), LOOKUP_TIMEOUT)
    # "write a poem about rain" is a writing task, not a weather question.
    writing = bool(_MAKE.search(text) and not _NEWSY.search(text))
    if widgets.weather_place(text) and not writing:
        jobs["weather"] = asyncio.wait_for(widgets.weather(text), LOOKUP_TIMEOUT)
    if widgets.stock_query(text) or re.search(r"\b(sensex|nifty)\b", text, re.I):
        jobs["stock"] = asyncio.wait_for(widgets.stock(text), LOOKUP_TIMEOUT)
    if search:
        # Weather and stock questions are answered by their live card; Pro's extra searches add nothing there.
        if pro and focus == "web" and not ("weather" in jobs or "stock" in jobs):
            jobs["search"] = asyncio.wait_for(_pro(text, model), PRO_TIMEOUT)
        else:
            jobs["search"] = asyncio.wait_for(_search(text, 8 if force else 5, focus, model),
                                              LOOKUP_TIMEOUT + READ_TIMEOUT)
        if force and focus == "web" and search_modes.wants_images(text):
            jobs["images"] = asyncio.wait_for(search_modes.images(text[:150], 6), LOOKUP_TIMEOUT)
    if focus == "web" and (videos if videos is not None else search and force) and search_modes.wants_videos(text):
        jobs["videos"] = asyncio.wait_for(search_modes.video(video_query(text), 4), LOOKUP_TIMEOUT + 4)
    if not jobs and (writing or not widgets.is_weather(text)):
        return empty
    found = dict(zip(jobs, await asyncio.gather(*jobs.values(), return_exceptions=True)))
    parts, cards, pictures, clips, live_cards, queries = [], [], [], [], [], []
    for name, item in found.items():
        if isinstance(item, Exception):
            logger.warning("Live lookup %s failed: %r", name, item)
        elif not item:
            continue
        elif name == "rates":
            parts.append(item)
        elif name in ("weather", "stock"):
            parts.insert(0, item[0])
            live_cards.append(item[1])
        elif name == "search":
            parts.append(item[0])
            cards = item[1]
            queries = list(item[2]) if len(item) > 2 else [text[:200]]
        elif name == "images":
            pictures = item
        elif name == "videos":
            # Shown as a row of YouTube videos under the sources; not numbered, so citations stay on the web cards.
            clips = [{"type": "clip", "title": v.get("title") or "YouTube video", "url": v["url"],
                      "thumbnail": v["thumbnail"], "domain": "youtube.com",
                      **({"channel": v["channel"]} if v.get("channel") else {})} for v in item]
    if widgets.is_weather(text) and not writing and not any(c.get("type") == "weather" for c in live_cards):
        parts.append(NO_WEATHER_NOTE if widgets.weather_place(text) else ASK_PLACE_NOTE)
    return {"context": "\n\n".join(parts) or None, "sources": live_cards + cards + pictures + clips,
            "queries": queries}


async def lookup(user_messages: List[str], search: bool = True) -> Optional[str]:
    """Live context for the latest question, or None when it doesn't need any (or the lookup fails)."""
    return (await gather(user_messages, search))["context"]
