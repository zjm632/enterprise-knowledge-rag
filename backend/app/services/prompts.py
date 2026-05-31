from pathlib import Path

from app.core.config import get_settings


PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def current_prompt_version() -> str:
    return get_settings().prompt_version
