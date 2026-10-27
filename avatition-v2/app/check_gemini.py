"""Check that Gemini works from this laptop.   Run:  python -m app.check_gemini"""
import sys

from app import gemini
from app.config import get_settings


def main() -> int:
    settings = get_settings()
    if not settings.gemini_api_key:
        print("No Gemini key yet. Save it with:  python -m app.set_gemini_key")
        return 1
    try:
        text = gemini.write_text("Reply with exactly: Gemini is connected.", "You are a test.", settings)
    except gemini.GeminiError as exc:
        print("Gemini is NOT working:", exc)
        return 1
    print("Gemini replied:", text)
    print("Model:", settings.gemini_model or f"first available of {', '.join(gemini.DEFAULT_MODELS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
