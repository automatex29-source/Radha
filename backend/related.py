"""Perplexity-style "Related" follow-up questions.

The model ends its reply with one line, "Related: q1 | q2 | q3". The line is cut from the saved reply and
kept as a list, which the chat shows as tappable questions. Asking in the same reply costs no extra request.
"""
import re
from typing import List, Tuple

PROMPT = (
    "After your answer, on its own last line, write \"Related: \" followed by three short follow-up questions the "
    "user might ask next, separated by \" | \". Write the questions in the user's language, but keep the word "
    "\"Related:\" in English. Write nothing after that line. Skip the line only for greetings and thanks."
)

_PATTERN = r"(?:^|\n)[ \t>*_#-]*\**{}\**:\**[ \t]*([^\n]*)\s*$"
_LINE = re.compile(_PATTERN.format("Related"), re.I)
_REPLIES = re.compile(_PATTERN.format("Replies"), re.I)  # the Counsellor's tap-to-answer replies


def split(text: str, line: re.Pattern = _LINE) -> Tuple[str, List[str]]:
    """(reply without the Related line, or another line pattern, and up to three items from it)."""
    found = line.search(text or "")
    if not found:
        return text, []
    questions = []
    for q in found.group(1).split("|"):
        q = q.strip().strip("*_\"' ").strip()
        q = re.sub(r"^\d+[.)]\s*", "", q)
        if 3 <= len(q) <= 160 and q not in questions:
            questions.append(q)
    return text[:found.start()].rstrip(), questions[:3]
