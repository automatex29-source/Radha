"""The Counsellor's Gita touch: a struggle gets a fitting verse, but never in a crisis, small talk or twice in a row."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import counsellor  # noqa: E402


def _chat(*turns):
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": t} for i, t in enumerate(turns)]


def test_a_struggle_asks_for_a_verse():
    assert counsellor.gita_note(_chat("I failed my exam again and I feel useless")) == counsellor.GITA_NOTE
    assert counsellor.gita_note(_chat("bahut tension hai yaar kuch samajh nahi aa raha")) == counsellor.GITA_NOTE
    assert counsellor.gita_note(_chat("मुझे बहुत डर लग रहा है कल के इंटरव्यू से")) == counsellor.GITA_NOTE


def test_no_verse_in_crisis_small_talk_or_right_after_one():
    assert counsellor.gita_note(_chat("I want to die, I failed everything")) == ""
    assert counsellor.gita_note(_chat("hi")) == ""
    assert counsellor.gita_note(_chat("I got the job today, so happy!!")) == ""
    after = _chat("I'm so stressed about exams", "> **Gita 2.47:** Your right is to your effort...",
                  "still stressed about the results")
    assert counsellor.gita_note(after) == "" and counsellor.verse_note(after) == counsellor.NO_VERSE
