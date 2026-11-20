"""Study mode for students in India: who the student is (class or exam, board, the language they learn in)
and the tutor instructions built from it.

Krish learns the profile from what the student writes ("class 10 CBSE", "NEET 2027", "Hindi medium") and
saves it on the user, so it stops asking "which class?" in every chat. The study rules (RULES) apply to any
study question; Study mode adds the hint-first tutor (PROMPT).
"""
import re
from typing import Optional

LEVELS = {
    "class-6-8": "a school student in Class 6 to 8",
    "class-9-10": "a school student in Class 9 or 10 (board exams)",
    "class-11-12": "a school student in Class 11 or 12 (board exams)",
    "jee": "preparing for JEE Main / Advanced (Physics, Chemistry, Maths)",
    "neet": "preparing for NEET (Physics, Chemistry, Biology)",
    "cuet": "preparing for CUET",
    "govt": "preparing for government exams (UPSC, SSC, banking, railways)",
    "college": "a college or university student",
}
SCHOOL = {"class-6-8", "class-9-10", "class-11-12"}
BOARDS = {"cbse": "CBSE (NCERT books)", "icse": "ICSE / ISC", "state": "a state board"}
LANGS = {
    "en": "Explain in simple English.",
    "hinglish": "Explain in easy Hinglish (Hindi in English letters), keeping technical terms in English.",
    "hi": "Explain in simple Hindi in Devanagari (Hindi medium), with the English term in brackets the first "
          "time a technical word comes up.",
}


def clean(profile) -> Optional[dict]:
    """Keep only known values; None when nothing useful is left."""
    if not isinstance(profile, dict):
        return None
    level = profile.get("level") if profile.get("level") in LEVELS else None
    board = profile.get("board") if level in SCHOOL and profile.get("board") in BOARDS else None
    lang = profile.get("lang") if profile.get("lang") in LANGS else None
    if not (level or lang):
        return None
    return {"level": level, "board": board, "lang": lang}


def profile_line(profile) -> str:
    """The system-prompt line about the student, or "" when they haven't picked anything."""
    p = clean(profile)
    if not p:
        return ""
    bits = []
    if p["level"]:
        who = f"The student is {LEVELS[p['level']]}"
        if p["board"]:
            who += f", on {BOARDS[p['board']]}"
        bits.append(who + ". Pitch every explanation, example and question at that level and syllabus, and "
                          "don't ask which class or exam they are in.")
    if p["lang"]:
        bits.append(LANGS[p["lang"]] + " If they write in another language, answer in theirs.")
    return " ".join(bits)


# The hint-first tutor: only when the Study button is on.
PROMPT = (
    "Study mode is on: be a patient tutor for a student in India. If their class or exam isn't known, ask once. "
    "Explain one idea at a time in simple words with an everyday Indian example, then ask one short question to "
    "check they understood. Homework: give hints and let them try; show the full solution when they try or ask."
)

# How to help with any study question, Study mode or not. Short paragraphs, so the free model's prompt trimming
# (agent/llm.py _shorten_prompt) keeps each one whole.
RULES = (
    "Study help rules:\n"
    "- Photo of a question: first write the question as you read it, then solve it step by step.\n"
    "- Attached chapter or PDF: crisp revision notes from it, then the questions most likely in the exam.\n"
    "\n- Follow their syllabus (NCERT for CBSE, NEET and JEE Main) and name the chapter. Boards: show how a "
    "full-marks answer is written. JEE/NEET: add the shortcut or trap.\n"
    "- Quiz me, MCQs or practice: use create_quiz (exam_marking for JEE/NEET), 5-10 questions, easy to hard. "
    "Flashcards: create_flashcards.\n"
    "- Exam plan: a realistic day-by-day plan to the exam date, with revision and mock tests."
)

_CLASS = re.compile(r"\b(?:class|std|standard|grade|kaksha)\s*(\d{1,2})(?:th)?\b|\b(\d{1,2})(?:th|vi)\s*(?:class|std|standard|grade)\b"
                    r"|\u0915\u0915\u094d\u0937\u093e\s*(\d{1,2})", re.I)  # कक्षा
_EXAMS = [("jee", re.compile(r"\b(?:iit[\s-]?)?jee\b|\biit\b", re.I)), ("neet", re.compile(r"\bneet\b", re.I)),
          ("cuet", re.compile(r"\bcuet\b", re.I)),
          ("govt", re.compile(r"\b(?:upsc|ssc|cgl|ibps|bank po|railways?|rrb|nda|cds)\b", re.I)),
          ("college", re.compile(r"\b(?:b\.?tech|btech|b\.?sc|bsc|b\.?com|bcom|ba|bba|bca|mbbs|college|semester|university)\b", re.I))]
_BOARDS = [("cbse", re.compile(r"\bcbse\b|\bncert\b", re.I)), ("icse", re.compile(r"\bi[cs]se\b|\bisc\b", re.I)),
           ("state", re.compile(r"\bstate board\b|\b(?:up|bihar|mp|rbse|maharashtra|hbse) board\b", re.I))]
_HINDI_MEDIUM = re.compile(r"\bhindi medium\b|\u0939\u093f\u0902\u0926\u0940 \u092e\u093e\u0927\u094d\u092f\u092e", re.I)


def detect(text: Optional[str]) -> dict:
    """What a message says about the student: {"level", "board", "lang"} for the parts it mentions."""
    text = text or ""
    found = {}
    m = _CLASS.search(text)
    if m:
        n = int(next(g for g in m.groups() if g))
        found["level"] = "class-6-8" if 6 <= n <= 8 else "class-9-10" if n in (9, 10) else \
            "class-11-12" if n in (11, 12) else None
        if not found["level"]:
            del found["level"]
    if "level" not in found or found["level"] == "class-11-12":
        for level, pat in _EXAMS:  # "class 12 + JEE" is a JEE student
            if pat.search(text):
                found["level"] = level
                break
    for board, pat in _BOARDS:
        if pat.search(text):
            found["board"] = board
            break
    if _HINDI_MEDIUM.search(text):
        found["lang"] = "hi"
    return found


def learn(profile, text: Optional[str]) -> Optional[dict]:
    """The profile updated with what this message says, or None when it adds nothing new."""
    found = detect(text)
    if not found:
        return None
    old = clean(profile) or {"level": None, "board": None, "lang": None}
    new = dict(old)
    if found.get("level") and found["level"] != old["level"]:
        new["level"] = found["level"]
        new["board"] = None  # a new class or exam: the old board may not fit
    if found.get("board"):
        new["board"] = found["board"]
    if found.get("lang"):
        new["lang"] = found["lang"]
    new = clean(new)
    return new if new and new != clean(profile) else None
