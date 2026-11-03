"""When a free AI provider's limit is hit, the user is told when it works again, not the raw provider error."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import friendly_errors as fe  # noqa: E402


class RateLimitError(Exception):
    pass


def test_wait_times_are_read_from_provider_errors():
    assert fe.wait_seconds("Rate limit reached for model gpt-oss-120b. Please try again in 7m12.5s.") == 432.5
    assert fe.wait_seconds("Please try again in 1h2m3s") == 3723
    assert fe.wait_seconds("try again in 820ms") is None  # under a second: "about a minute"
    assert fe.wait_seconds('quota exceeded "retryDelay": "34s"') == 34
    assert fe.wait_seconds("Too many requests") is None


def test_limit_message_says_when_it_works_again():
    msg = fe.friendly(RateLimitError("Rate limit reached on tokens per day (TPD). Please try again in 7m12s."))
    assert "daily limit" in msg["message"] and "works again at " in msg["message"] and msg["resetsAt"] and msg["daily"]
    assert "another model" in msg["message"]
    short = fe.friendly(Exception("429 Too Many Requests"))
    assert "about a minute" in short["message"] and short["resetsAt"] is None
    daily = fe.friendly(Exception("You exceeded your current quota of requests per day"))
    assert "once a day" in daily["message"]


def test_other_errors_are_not_limits():
    assert fe.friendly(Exception("HarmonyError: Tools should have a name!")) is None
    assert "Regenerate" in fe.SHORT_ERROR
