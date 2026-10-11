"""Interactive German article flashcard quiz CLI application."""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import random
import re
import sys

# ANSI color codes for terminal formatting
CYAN = "\033[96m"
DARK_GRAY = "\033[90m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

CARD_PATTERN = re.compile(r"^[^;]+;[^;]+;[^;]+")
QUIZ_LENGTH = 20

@dataclass(frozen=True)
class Flashcard:
    """Represents a German vocabulary flashcard item."""
    article: str
    noun: str
    translation: str

def load_cards(file_path: Path) -> list[Flashcard]:
    """Reads and parses semicolon-delimited flashcards from a file."""
    if not file_path.is_file():
        sys.stderr.write(f"Articles file not found at: '{file_path}'\n")
        return []

    cards: list[Flashcard] = []

    with file_path.open("r", encoding="utf-8") as file:
        for line in file:
            trimmed = line.strip()
            if not trimmed or not CARD_PATTERN.match(trimmed):
                continue
            parts = trimmed.split(";")
            cards.append(
                Flashcard(
                    article=parts[0].strip().lower(),
                    noun=parts[1].strip(),
                    translation=parts[2].strip(),
                )
            )
    return cards


def save_results(
    results_path: Path,
    correct: int,
    wrong: int,
    wrong_nouns: list[str],
) -> None:
    """Appends quiz results to a results file for trend and progress reporting."""
    record = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": correct + wrong,
        "right": correct,
        "wrong": wrong,
        "wrong_nouns": wrong_nouns,
    }
    with results_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def ask_play_again() -> bool:
    """Prompts the user whether to take a new quiz or close."""
    while True:
        try:
            choice = input(
                "\nWould you like to take a new quiz? (y = yes, n = exit): "
            ).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            return False

        if choice in {"y", "yes", "1"}:
            return True
        if choice in {"n", "no", "q", "quit", "exit", "2"}:
            return False
        print(f"{YELLOW}Please enter 'y' to take a new quiz or 'n' to exit.{RESET}")


def run_quiz_session(
    cards: list[Flashcard],
    target_results_path: Path,
    options: dict[str, str],
) -> bool:
    """Executes a single quiz session and saves results. Returns False if user aborted."""
    quiz_cards = random.sample(cards, min(QUIZ_LENGTH, len(cards)))
    total = 0
    correct = 0
    wrong_nouns: list[str] = []
    user_quit = False

    print(f"\n{CYAN}=== German Article Quiz ({len(quiz_cards)} questions) ==={RESET}")
    print(f"{DARK_GRAY}Select 1, 2, or 3 (or type der/die/das). Enter 'q' to quit.{RESET}\n")

    try:
        for idx, card in enumerate(quiz_cards, start=1):
            while True:
                print(
                    f"[{idx}/{len(quiz_cards)}] "
                    f"{YELLOW}{card.noun} ({card.translation}){RESET}"
                )
                print("  1. Der\n  2. Die\n  3. Das")
                answer = input("Choice: ").strip().lower()

                if answer in {"q", "quit", "exit"}:
                    user_quit = True
                    break

                if answer not in options:
                    print(
                        f"{YELLOW}Invalid choice. "
                        f"Please choose 1, 2, 3 or type the article.{RESET}\n"
                    )
                    continue

                total += 1
                if options[answer] == card.article:
                    correct += 1
                    print(f"{GREEN}Correct! ({card.article} {card.noun}){RESET}\n")
                else:
                    wrong_nouns.append(card.noun)
                    print(
                        f"{RED}Wrong! The correct article is: "
                        f"{card.article} ({card.article} {card.noun}){RESET}\n"
                    )
                break

            if user_quit:
                break
    except (KeyboardInterrupt, EOFError):
        print()
        user_quit = True

    if total > 0:
        wrong = total - correct
        percent = round((correct / total) * 100)
        print(f"\n{CYAN}Quiz finished! Score: {correct} / {total} ({percent}%){RESET}")
        save_results(target_results_path, correct, wrong, wrong_nouns)
        print(f"{DARK_GRAY}Results saved to '{target_results_path.name}'.{RESET}")

    return not user_quit


def start_article_quiz(file_path: Path, results_path: Path | None = None) -> None:
    """Runs the interactive German article quiz with replay prompting."""
    cards = load_cards(file_path)
    if not cards:
        return

    target_results_path = (
        results_path if results_path is not None else file_path.parent / "results.txt"
    )
    options = {
        "1": "der", "2": "die", "3": "das",
        "der": "der", "die": "die", "das": "das",
    }

    while True:
        completed_normally = run_quiz_session(cards, target_results_path, options)
        if not completed_normally:
            break
        if not ask_play_again():
            break


def main() -> None:
    """Parses command-line arguments and starts the article quiz."""
    default_path = Path(__file__).resolve().parent / "articles.txt"
    parser = argparse.ArgumentParser(
        description="Runs an interactive German article flashcard quiz."
    )
    parser.add_argument(
        "file_path",
        nargs="?",
        default=default_path,
        type=Path,
        help="Path to the vocabulary file (default: articles.txt in script directory).",
    )
    args = parser.parse_args()
    start_article_quiz(args.file_path)

if __name__ == "__main__":
    main()
