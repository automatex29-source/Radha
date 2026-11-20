"""Quizzes and flashcards show plain text, so formulas the model writes in LaTeX must read as normal maths."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import flashcards, quiz  # noqa: E402
from agent.plain_math import plain_math  # noqa: E402


def test_latex_becomes_readable_text():
    assert plain_math(r"so $\frac{3}{7}$ and $\frac{2}{7}$ are like") == "so 3/7 and 2/7 are like"
    assert plain_math(r"$x^{2} + 3x \times 2 = 0$") == "x² + 3x × 2 = 0"
    assert plain_math(r"\(\sqrt{16} = 4\)") == "√16 = 4"
    assert plain_math(r"$\theta = 30^\circ$") == "θ = 30°"
    assert plain_math(r"$H_2O$") == "H₂O"
    assert plain_math(r"$\frac{a+b}{2}$") == "(a+b)/2"


def test_prices_and_plain_text_are_kept():
    assert plain_math("Costs $5 and $10 today") == "Costs $5 and $10 today"
    assert plain_math("Who was the first Mughal emperor?") == "Who was the first Mughal emperor?"


def test_quiz_and_flashcards_use_it():
    q = quiz.clean_questions([{"question": r"Which pair is like fractions?",
                               "options": [r"$\frac{1}{2}$ and $\frac{3}{4}$", r"$\frac{3}{7}$ and $\frac{2}{7}$"],
                               "answer": 1, "explain": r"Same denominator: $\frac{3}{7}$, $\frac{2}{7}$"}])[0]
    assert q["o"] == ["1/2 and 3/4", "3/7 and 2/7"] and "\\" not in q["e"] and "$" not in q["e"]
    card = flashcards.clean_cards([{"front": r"$\sqrt{81}$", "back": "9"}])[0]
    assert card["front"] == "√81"
