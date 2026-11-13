"""Study mode for students in India: who the student is (class or exam, board, the language they learn in)
and the tutor instructions built from it.

The profile is picked on the Study screen and saved on the user, so Krish stops asking "which class?" in
every chat.
"""
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


PROMPT = (
    "Study mode is on: be a patient tutor for a student in India. If their class or exam isn't known, ask once. "
    "Explain one idea at a time in simple words with an everyday Indian example, then ask one short question to "
    "check they understood. Homework: give hints and let them try; show the full solution when they try or ask.\n\n"
    "- Photo of a question: first write the question as you read it, then solve it step by step.\n"
    "- Attached chapter or PDF: crisp revision notes from it, then the questions most likely in the exam.\n"
    "\n- Follow their syllabus (NCERT for CBSE, NEET and JEE Main) and name the chapter. Boards: show how a "
    "full-marks answer is written. JEE/NEET: add the shortcut or trap.\n"
    "- Quiz me, MCQs or practice: use create_quiz (exam_marking for JEE/NEET), 5-10 questions, easy to hard. "
    "After a topic, offer a quiz or flashcards (create_flashcards).\n"
    "- Exam plan: a realistic day-by-day plan to the exam date, with revision and mock tests."
)
