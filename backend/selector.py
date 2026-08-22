import os

import scripting as s

from .assistant import run_assistant
from .local_selector import SUPPORTED_LANGS, run_local_assistant

VALID_MODES = ("local", "claude")


def get_mode() -> str:
    mode = os.environ.get("AI_MODE", "local").lower()
    return mode if mode in VALID_MODES else "local"


def get_supported_langs() -> list[str]:
    """Languages the active mode can actually understand - the local matcher
    only covers a couple of languages, Claude understands every dataset
    language. Used to keep the frontend from offering a language that will
    silently fail to match anything."""
    if get_mode() == "claude":
        return s.list_languages()
    return sorted(SUPPORTED_LANGS)


def run_selector(message: str, history: list[dict], lang: str) -> dict:
    if get_mode() == "claude":
        return run_assistant(message, history, lang)
    return run_local_assistant(message, history, lang)
