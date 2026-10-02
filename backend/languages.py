"""The app language a person picks in Settings. Krish answers in it; the interface text follows it too."""
from typing import Optional

# code -> English name (what the model reads)
LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "ur": "Urdu",
    "es": "Spanish",
    "fr": "French",
    "ar": "Arabic",
}
DEFAULT = "en"


def normalize(code: Optional[str]) -> str:
    return code if code in LANGUAGES else DEFAULT


def prompt_line(code: Optional[str]) -> Optional[str]:
    """The system-prompt line for a chosen language; none for English, the default."""
    code = normalize(code)
    if code == DEFAULT:
        return None
    name = LANGUAGES[code]
    return (f"The person set {name} as their language in Settings. Always reply in {name}, written in its own "
            f"script, even when they write in another language, unless they ask you to use a different language. "
            "Keep code, links and names as they are.")
