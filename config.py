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


class Config:  # pylint: disable=too-few-public-methods
    """Global configuration settings and shared utilities."""

    QUIZ_LENGTH: int = 20
    DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
    DEFAULT_VOCAB_FILE: str = "articles.txt"
    DEFAULT_RESULTS_FILE: str = "results.txt"
    DEFAULT_DB_FILE: str = "quiz_history.db"

    CASE_CONFIGS: dict[str, dict] = {
        "nominativ": {
            "name": "Nominativ",
            "vocab_file": "articles.txt",
            "results_file": "results.txt",
            "db_file": "quiz_history.db",
            "options": {
                "1": "der", "2": "die", "3": "das",
                "der": "der", "die": "die", "das": "das",
            },
            "labels": ["Der", "Die", "Das"],
        },
        "akkusativ": {
            "name": "Akkusativ",
            "vocab_file": "articles_accusative.txt",
            "results_file": "results_akkusativ.txt",
            "db_file": "quiz_history.db",
            "options": {
                "1": "den", "2": "die", "3": "das",
                "den": "den", "die": "die", "das": "das",
            },
            "labels": ["Den", "Die", "Das"],
        },
        "dativ": {
            "name": "Dativ",
            "vocab_file": "articles_dative.txt",
            "results_file": "results_dativ.txt",
            "db_file": "quiz_history.db",
            "options": {
                "1": "dem", "2": "der", "3": "den",
                "dem": "dem", "der": "der", "den": "den",
            },
            "labels": ["Dem", "Der", "Den (Plural)"],
        },
    }

    ARTICLE_OPTIONS: dict[str, str] = CASE_CONFIGS["nominativ"]["options"]

    COLORS: Colors = Colors()

    @classmethod
    def current_timestamp(cls) -> str:
        """Returns current timestamp formatted according to DATE_FORMAT."""
        return datetime.now().strftime(cls.DATE_FORMAT)
