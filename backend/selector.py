import os

from .assistant import run_assistant
from .local_selector import run_local_assistant

VALID_MODES = ("local", "claude")


def get_mode() -> str:
    mode = os.environ.get("AI_MODE", "local").lower()
    return mode if mode in VALID_MODES else "local"


def run_selector(message: str, history: list[dict], lang: str) -> dict:
    if get_mode() == "claude":
        return run_assistant(message, history, lang)
    return run_local_assistant(message, history, lang)
