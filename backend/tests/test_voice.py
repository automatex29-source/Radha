"""Offline tests for voice input: free Groq Whisper when there's no OpenAI key."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import media  # noqa: E402


class FakeClient:
    calls = []
    text = "namaste RADHA"
    language = "english"

    def __init__(self, api_key=None, base_url=None):
        self.base_url = base_url
        client = self

        class Transcriptions:
            async def create(self, **kw):
                FakeClient.calls.append({"base_url": client.base_url, **kw})
                return type("R", (), {"text": FakeClient.text, "language": FakeClient.language})()

        self.audio = type("A", (), {"transcriptions": Transcriptions()})()


@pytest.fixture
def fake_openai(monkeypatch):
    import openai

    FakeClient.calls = []
    FakeClient.text, FakeClient.language = "namaste RADHA", "english"
    monkeypatch.setattr(openai, "AsyncOpenAI", FakeClient)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    return monkeypatch


def test_no_keys_means_no_voice(fake_openai):
    assert not media.transcription_available()
    with pytest.raises(media.MediaUnavailable):
        asyncio.run(media.transcribe(b"x", "a.webm"))


def test_groq_whisper_used_without_openai(fake_openai):
    fake_openai.setenv("GROQ_API_KEY", "gsk_test")
    assert media.transcription_available()
    text = asyncio.run(media.transcribe(b"audio", "a.webm", "hi"))
    assert text == "namaste RADHA"
    call = FakeClient.calls[-1]
    assert call["base_url"] == media.GROQ_BASE_URL
    assert call["model"] == media.GROQ_STT_MODEL
    assert call["language"] == "hi"


def test_openai_preferred_when_set(fake_openai):
    fake_openai.setenv("GROQ_API_KEY", "gsk_test")
    fake_openai.setenv("OPENAI_API_KEY", "sk_test")
    asyncio.run(media.transcribe(b"audio", "a.webm"))
    call = FakeClient.calls[-1]
    assert call["model"] == media.STT_MODEL and "language" not in call


def test_edge_voice_follows_language_or_script():
    assert media.edge_voice("hello", "ta") == media.EDGE_VOICES["ta"]
    assert media.edge_voice("नमस्ते दोस्त", "auto") == media.EDGE_VOICES["hi"]
    assert media.edge_voice("வணக்கம்", None) == media.EDGE_VOICES["ta"]
    assert media.edge_voice("হ্যালো", None) == media.EDGE_VOICES["bn"]
    assert media.edge_voice("Hello there", "auto") == media.EDGE_VOICES["en"]
    assert len(media.VOICE_LANGUAGES) >= 10


def test_phantom_transcripts_are_dropped():
    assert media.clean_transcript(" Thank you. ") == ""
    assert media.clean_transcript("धन्यवाद") == ""
    assert media.clean_transcript("Thank you for the help") == "Thank you for the help"


def test_spoken_language_is_detected(fake_openai):
    fake_openai.setenv("GROQ_API_KEY", "gsk_test")
    FakeClient.text, FakeClient.language = "kaise ho", "Hindi"
    assert asyncio.run(media.transcribe_detect(b"a", "a.webm")) == ("kaise ho", "hi")
    assert FakeClient.calls[-1]["response_format"] == "verbose_json"
    # The script wins over Whisper's label (it often mixes up Hindi and Urdu).
    FakeClient.text, FakeClient.language = "आप कैसे हैं", "urdu"
    assert asyncio.run(media.transcribe_detect(b"a", "a.webm"))[1] == "hi"
    FakeClient.text, FakeClient.language = "ਸਤ ਸ੍ਰੀ ਅਕਾਲ", "punjabi"
    assert asyncio.run(media.transcribe_detect(b"a", "a.webm"))[1] == "pa"
    FakeClient.text, FakeClient.language = "hola amigo", "spanish"
    assert asyncio.run(media.transcribe_detect(b"a", "a.webm"))[1] == "es"


def test_voice_prompt_follows_spoken_language():
    import os
    for k, v in {"MONGO_URL": "mongodb://x", "DB_NAME": "x", "JWT_SECRET": "x"}.items():
        os.environ.setdefault(k, v)
    import server
    assert "reply in Tamil" in server.voice_prompt("ta", "hi")
    assert "use Hindi" in server.voice_prompt("auto", "hi")
    assert "use" not in server.voice_prompt(None, None).split("Hindi and English, mix the same way.")[-1]
