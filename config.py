"""Configuration settings, terminal colors, and shared constants."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Colors:  # pylint: disable=too-few-public-methods
    """ANSI color codes for terminal output formatting."""

    cyan: str = "\033[96m"
    dark_gray: str = "\033[90m"
    yellow: str = "\033[93m"
    green: str = "\033[92m"
    red: str = "\033[91m"
    reset: str = "\033[0m"


def _make_options(*articles: str) -> dict[str, str]:
    """Builds a choice mapping accepting 1-based numbers or article names."""
    options = {str(i): art for i, art in enumerate(articles, start=1)}
    options.update({art: art for art in articles})
    return options


class Config:  # pylint: disable=too-few-public-methods
    """Global configuration settings and shared utilities."""

    QUIZ_LENGTH: int = 20
    DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
    DEFAULT_DB_FILE: str = "quiz_history.db"

    CASE_CONFIGS: dict[str, dict] = {
        "nominativ": {
            "name": "Nominativ",
            "vocab_file": "articles.txt",
            "results_file": "results.txt",
            "options": _make_options("der", "die", "das"),
            "labels": ["Der", "Die", "Das"],
        },
        "akkusativ": {
            "name": "Akkusativ",
            "vocab_file": "articles_accusative.txt",
            "results_file": "results_akkusativ.txt",
            "options": _make_options("den", "die", "das"),
            "labels": ["Den", "Die", "Das"],
        },
        "dativ": {
            "name": "Dativ",
            "vocab_file": "articles_dative.txt",
            "results_file": "results_dativ.txt",
            "options": _make_options("dem", "der", "den"),
            "labels": ["Dem", "Der", "Den (Plural)"],
        },
    }

    COLORS: Colors = Colors()

    @classmethod
    def current_timestamp(cls) -> str:
        """Returns current timestamp formatted according to DATE_FORMAT."""
        return datetime.now().strftime(cls.DATE_FORMAT)
