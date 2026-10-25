"""Panchang: tithi, nakshatra, yoga, karana, lunar month and Hindu festivals, worked out from the Sun and Moon.

Positions use the shortened formulas in Jean Meeus' Astronomical Algorithms (the Moon to about 0.05 degrees),
the Lahiri ayanamsa and the amanta month (new moon to new moon). That puts tithi and nakshatra end times within a
few minutes of printed panchangs; festivals follow the tithi at sunrise, so a local calendar can differ by a day.
"""
import math
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

TITHIS = ["Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi", "Saptami", "Ashtami", "Navami",
          "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi"]
NAKSHATRAS = ["Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha",
              "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
              "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
              "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"]
YOGAS = ["Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda", "Sukarma", "Dhriti", "Shula",
         "Ganda", "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha",
         "Shiva", "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti"]
KARANAS = ["Bava", "Balava", "Kaulava", "Taitila", "Garaja", "Vanija", "Vishti"]
MONTHS = ["Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada", "Ashwin", "Kartika",
          "Margashirsha", "Pausha", "Magha", "Phalguna"]
RASIS = ["Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya", "Tula", "Vrishchika", "Dhanu", "Makara",
         "Kumbha", "Meena"]
VARAS = ["Somavara (Monday)", "Mangalavara (Tuesday)", "Budhavara (Wednesday)", "Guruvara (Thursday)",
         "Shukravara (Friday)", "Shanivara (Saturday)", "Ravivara (Sunday)"]

# (amanta month, tithi 1-30: 1-15 Shukla, 16-29 Krishna, 30 Amavasya) -> festival
FESTIVALS = {
    ("Chaitra", 1): "Ugadi / Gudi Padwa (Hindu New Year), Chaitra Navratri begins",
    ("Chaitra", 9): "Ram Navami", ("Chaitra", 15): "Hanuman Jayanti",
    ("Vaishakha", 3): "Akshaya Tritiya", ("Vaishakha", 15): "Buddha Purnima",
    ("Jyeshtha", 11): "Nirjala Ekadashi", ("Ashadha", 2): "Jagannath Rath Yatra",
    ("Ashadha", 11): "Devshayani Ekadashi", ("Ashadha", 15): "Guru Purnima",
    ("Shravana", 5): "Nag Panchami", ("Shravana", 15): "Raksha Bandhan", ("Shravana", 23): "Krishna Janmashtami",
    ("Bhadrapada", 3): "Hartalika Teej", ("Bhadrapada", 4): "Ganesh Chaturthi", ("Bhadrapada", 14): "Anant Chaturdashi",
    ("Bhadrapada", 30): "Mahalaya Amavasya",
    ("Ashwin", 1): "Sharad Navratri begins", ("Ashwin", 8): "Durga Ashtami", ("Ashwin", 9): "Maha Navami",
    ("Ashwin", 10): "Dussehra (Vijayadashami)", ("Ashwin", 15): "Sharad Purnima", ("Ashwin", 19): "Karwa Chauth",
    ("Ashwin", 28): "Dhanteras", ("Ashwin", 29): "Naraka Chaturdashi (Choti Diwali)",
    ("Ashwin", 30): "Diwali (Lakshmi Puja)",
    ("Kartika", 1): "Govardhan Puja", ("Kartika", 2): "Bhai Dooj", ("Kartika", 6): "Chhath Puja",
    ("Kartika", 11): "Dev Uthani Ekadashi", ("Kartika", 15): "Kartik Purnima, Guru Nanak Jayanti",
    ("Margashirsha", 11): "Gita Jayanti (Mokshada Ekadashi)",
    ("Magha", 5): "Vasant Panchami", ("Magha", 29): "Maha Shivaratri",
    ("Phalguna", 15): "Holika Dahan", ("Phalguna", 16): "Holi",
}
# Festivals kept at a time of day other than sunrise: the tithi at that time decides the day.
KALA_HOURS = {"midday": 6, "afternoon": 8.5, "evening": 12, "night": 18}  # hours after sunrise
KALA = {"Ram Navami": "midday", "Ganesh Chaturthi": "midday", "Dussehra (Vijayadashami)": "afternoon",
        "Karwa Chauth": "evening", "Dhanteras": "evening", "Naraka Chaturdashi (Choti Diwali)": "evening",
        "Diwali (Lakshmi Puja)": "evening", "Holika Dahan": "evening", "Krishna Janmashtami": "night",
        "Maha Shivaratri": "night"}
SANKRANTIS = {270: "Makar Sankranti / Pongal", 0: "Mesha Sankranti (Baisakhi, Vishu, Puthandu)"}

AYANAMSA_2000 = 23.853  # Lahiri, degrees at J2000
AYANAMSA_RATE = 50.2788 / 3600  # degrees a year


def _jd(t: datetime) -> float:
    return t.timestamp() / 86400 + 2440587.5


def _sin(deg: float) -> float:
    return math.sin(math.radians(deg))


def sun_longitude(t: datetime) -> float:
    T = (_jd(t) - 2451545.0) / 36525
    L0 = 280.46646 + 36000.76983 * T
    M = 357.52911 + 35999.05029 * T
    C = (1.914602 - 0.004817 * T) * _sin(M) + (0.019993 - 0.000101 * T) * _sin(2 * M) + 0.000289 * _sin(3 * M)
    return (L0 + C - 0.00569 - 0.00478 * _sin(125.04 - 1934.136 * T)) % 360


_MOON_TERMS = [  # (D, M, M', F, coefficient in millionths of a degree)
    (0, 0, 1, 0, 6288774), (2, 0, -1, 0, 1274027), (2, 0, 0, 0, 658314), (0, 0, 2, 0, 213618),
    (0, 1, 0, 0, -185116), (0, 0, 0, 2, -114332), (2, 0, -2, 0, 58793), (2, -1, -1, 0, 57066),
    (2, 0, 1, 0, 53322), (2, -1, 0, 0, 45758), (0, 1, -1, 0, -40923), (1, 0, 0, 0, -34720),
    (0, 1, 1, 0, -30383), (2, 0, 0, -2, 15327), (0, 0, 1, 2, -12528), (0, 0, 1, -2, 10980),
    (4, 0, -1, 0, 10675), (0, 0, 3, 0, 10034), (4, 0, -2, 0, 8548), (2, 1, -1, 0, -7888),
    (2, 1, 0, 0, -6766), (1, 0, -1, 0, -5163), (1, 1, 0, 0, 4987), (2, -1, 1, 0, 4036),
    (2, 0, 2, 0, 3994), (4, 0, 0, 0, 3861), (2, 0, -3, 0, 3665), (0, 1, -2, 0, -2689),
    (2, 0, -1, 2, -2602), (2, -1, -2, 0, 2390), (1, 0, 1, 0, -2348), (2, -2, 0, 0, 2236),
]


def moon_longitude(t: datetime) -> float:
    T = (_jd(t) - 2451545.0) / 36525
    Lp = 218.3164477 + 481267.88123421 * T
    D = 297.8501921 + 445267.1114034 * T
    M = 357.5291092 + 35999.0502909 * T
    Mp = 134.9633964 + 477198.8675055 * T
    F = 93.2720950 + 483202.0175233 * T
    E = 1 - 0.002516 * T
    total = 0.0
    for d, m, mp, f, c in _MOON_TERMS:
        total += c * (E ** abs(m)) * _sin(d * D + m * M + mp * Mp + f * F)
    return (Lp + total / 1e6 - 0.00478 * _sin(125.04 - 1934.136 * T)) % 360


def ayanamsa(t: datetime) -> float:
    return AYANAMSA_2000 + (_jd(t) - 2451545.0) / 365.25 * AYANAMSA_RATE


def _elongation(t: datetime) -> float:
    return (moon_longitude(t) - sun_longitude(t)) % 360


def tithi_index(t: datetime) -> int:
    """0-29: 0-14 Shukla Pratipada to Purnima, 15-29 Krishna Pratipada to Amavasya."""
    return int(_elongation(t) // 12)


def nakshatra_index(t: datetime) -> int:
    return int(((moon_longitude(t) - ayanamsa(t)) % 360) // (360 / 27))


def yoga_index(t: datetime) -> int:
    total = (sun_longitude(t) + moon_longitude(t) - 2 * ayanamsa(t)) % 360
    return int(total // (360 / 27))


def karana_name(t: datetime) -> str:
    k = int(_elongation(t) // 6)
    if k == 0:
        return "Kimstughna"
    if k >= 57:
        return ["Shakuni", "Chatushpada", "Naga"][k - 57]
    return KARANAS[(k - 1) % 7]


def tithi_name(i: int) -> str:
    paksha = "Shukla" if i < 15 else "Krishna"
    if i == 14:
        return "Shukla Purnima"
    if i == 29:
        return "Krishna Amavasya"
    return f"{paksha} {TITHIS[i % 15]}"


def _ends(t: datetime, fn, step_hours: float = 1.0, limit_hours: int = 40) -> Optional[datetime]:
    """When fn(t) next changes, to the minute."""
    start = fn(t)
    lo = t
    for _ in range(int(limit_hours / step_hours)):
        hi = lo + timedelta(hours=step_hours)
        if fn(hi) != start:
            while hi - lo > timedelta(minutes=1):
                mid = lo + (hi - lo) / 2
                if fn(mid) == start:
                    lo = mid
                else:
                    hi = mid
            return hi
        lo = hi
    return None


def new_moon_before(t: datetime) -> datetime:
    guess = t - timedelta(days=_elongation(t) / 12.19)
    for _ in range(6):
        e = _elongation(guess)
        e = e - 360 if e > 180 else e
        guess -= timedelta(days=e / 12.19)
    return guess


def lunar_month(t: datetime) -> str:
    """Amanta month at t; 'Adhik' when no sankranti falls in it."""
    nm = new_moon_before(t)
    nxt = new_moon_before(nm + timedelta(days=31))
    r1 = int(((sun_longitude(nm) - ayanamsa(nm)) % 360) // 30)
    r2 = int(((sun_longitude(nxt) - ayanamsa(nxt)) % 360) // 30)
    name = MONTHS[(r1 + 1) % 12]
    return f"Adhik {name}" if r1 == r2 else name


def sunrise(day: date, lat: float, lon: float) -> datetime:
    """UTC sunrise (NOAA's formula, about a minute off)."""
    n = day.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g)
                       - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    lat_r = math.radians(lat)
    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(lat_r) * math.cos(decl))) - math.tan(lat_r) * math.tan(decl)
    ha = math.degrees(math.acos(max(-1.0, min(1.0, cos_ha))))
    minutes = 720 - 4 * (lon + ha) - eqtime
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(minutes=minutes)


def _festival_at(day: date, lat: float, lon: float, kala: str):
    t = sunrise(day, lat, lon) + timedelta(hours=KALA_HOURS.get(kala, 0))
    name = FESTIVALS.get((lunar_month(t), tithi_index(t) + 1))
    return name if name and KALA.get(name, "sunrise") == kala else None


def festivals_on(day: date, lat: float, lon: float) -> List[str]:
    rise = sunrise(day, lat, lon)
    nxt = sunrise(day + timedelta(days=1), lat, lon)
    ti = tithi_index(rise) + 1
    out = []
    for kala in ("sunrise", *KALA_HOURS):
        name = _festival_at(day, lat, lon, kala)
        # A long tithi can hold the same time on two days: the festival is the first of them.
        if name and name != _festival_at(day - timedelta(days=1), lat, lon, kala):
            out.append(name)
    if not out and ti in (11, 26):
        out.append(f"{'Shukla' if ti == 11 else 'Krishna'} Ekadashi (fasting day)")
    elif not out and ti == 15:
        out.append("Purnima (full moon)")
    elif not out and ti == 30:
        out.append("Amavasya (new moon)")
    elif not out and ti == 19:
        out.append("Sankashti Chaturthi")
    s1 = (sun_longitude(rise) - ayanamsa(rise)) % 360
    s2 = (sun_longitude(nxt) - ayanamsa(nxt)) % 360
    for deg, name in SANKRANTIS.items():
        if (s1 < deg <= s2) or (deg == 0 and s1 > s2):
            out.append(name)
    return out


def day_panchang(day: date, lat: float, lon: float, tz) -> dict:
    rise = sunrise(day, lat, lon)
    ti = tithi_index(rise)
    nk = nakshatra_index(rise)

    def local(t: Optional[datetime]) -> str:
        return t.astimezone(tz).strftime("%d %b, %I:%M %p") if t else "beyond tomorrow"

    sun_sid = (sun_longitude(rise) - ayanamsa(rise)) % 360
    moon_sid = (moon_longitude(rise) - ayanamsa(rise)) % 360
    return {
        "date": day.isoformat(), "vara": VARAS[day.weekday()], "sunrise": local(rise),
        "tithi": tithi_name(ti), "tithiEnds": local(_ends(rise, tithi_index)),
        "nakshatra": NAKSHATRAS[nk], "nakshatraEnds": local(_ends(rise, nakshatra_index)),
        "yoga": YOGAS[yoga_index(rise)], "karana": karana_name(rise),
        "paksha": "Shukla (waxing)" if ti < 15 else "Krishna (waning)",
        "month": lunar_month(rise) + " (amanta)", "sunSign": RASIS[int(sun_sid // 30)],
        "moonSign": RASIS[int(moon_sid // 30)], "festivals": festivals_on(day, lat, lon),
    }
