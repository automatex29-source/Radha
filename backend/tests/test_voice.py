"""Offline tests for voice input: free Groq Whisper when there's no OpenAI key."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import media  # noqa: E402


class FakeClient:
    calls = []

    def __init__(self, api_key=None, base_url=None):
        self.base_url = base_url
        client = self

        class Transcriptions:
            async def create(self, **kw):
                FakeClient.calls.append({"base_url": client.base_url, **kw})
                return type("R", (), {"text": "namaste RADHA"})()

        self.audio = type("A", (), {"transcriptions": Transcriptions()})()


@pytest.fixture
def fake_openai(monkeypatch):
    import openai

    FakeClient.calls = []
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
