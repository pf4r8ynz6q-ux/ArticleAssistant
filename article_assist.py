"""Interactive German article flashcard quiz CLI application."""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import random
import re
import sys

from config import Config
import db

COLORS = Config.COLORS
CARD_PATTERN = re.compile(r"^[^;]+;[^;]+;[^;]+")

@dataclass(frozen=True)
class Flashcard:  # pylint: disable=too-few-public-methods
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
        "date": Config.current_timestamp(),
        "total": correct + wrong,
        "right": correct,
        "wrong": wrong,
        "wrong_nouns": wrong_nouns,
    }
    with results_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_review_cards(
    cards: list[Flashcard],
    db_path: Path,
    count: int = Config.QUIZ_LENGTH,
    case: str = "nominativ",
) -> list[Flashcard]:
    """Selects flashcards that have past errors, prioritized by lowest success rate."""
    cards_by_noun = {card.noun: card for card in cards}
    troubled_nouns = db.get_troubled_nouns(db_path, count, case=case)

    selected = [
        cards_by_noun[noun] for noun in troubled_nouns if noun in cards_by_noun
    ]
    troubled_count = len(selected)

    if len(selected) < count:
        selected_set = {card.noun for card in selected}
        remaining = [card for card in cards if card.noun not in selected_set]
        selected.extend(random.sample(remaining, min(count - len(selected), len(remaining))))

    random.shuffle(selected)
    case_name = Config.CASE_CONFIGS.get(case, {}).get("name", case.capitalize())
    if troubled_count > 0:
        filler_msg = (
            f" (plus {len(selected) - troubled_count} random)"
            if len(selected) > troubled_count
            else ""
        )
        print(
            f"{COLORS.cyan}Review Mode ({case_name}): Selected "
            f"{troubled_count} reinforcement noun(s){filler_msg}.{COLORS.reset}"
        )
    else:
        print(
            f"{COLORS.cyan}Review Mode ({case_name}): No troubled nouns found! "
            f"Practicing with {len(selected)} random noun(s).{COLORS.reset}"
        )
    return selected


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
        print(f"{COLORS.yellow}Please enter 'y' to take a new quiz or 'n' to exit.{COLORS.reset}")


def _prompt_card_choice(
    card: Flashcard,
    idx: int,
    total_cards: int,
    options: dict[str, str],
    labels: list[str],
) -> str | None:
    """Prompts the user for their choice on a card. Returns article choice or None if quitting."""
    while True:
        print(
            f"[{idx}/{total_cards}] "
            f"{COLORS.yellow}{card.noun} ({card.translation}){COLORS.reset}"
        )
        for i, label in enumerate(labels, start=1):
            print(f"  {i}. {label}")
        answer = input("Choice: ").strip().lower()

        if answer in {"q", "quit", "exit"}:
            return None

        if answer not in options:
            valid_nums = "/".join(str(i) for i in range(1, len(labels) + 1))
            print(
                f"{COLORS.yellow}Invalid choice. Please choose {valid_nums} "
                f"or type the article.{COLORS.reset}\n"
            )
            continue

        return options[answer]


def _record_quiz_summary(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    target_results_path: Path,
    db_path: Path,
    mode: str,
    attempts: list[tuple[str, str, str, int, str]],
    wrong_nouns: list[str],
    case: str = "nominativ",
) -> None:
    """Calculates and prints final score, then persists session to disk and database."""
    total = len(attempts)
    correct = sum(is_corr for _, _, _, is_corr, _ in attempts)
    wrong = total - correct
    percent = round((correct / total) * 100)
    print(f"\n{COLORS.cyan}Quiz finished! Score: {correct} / {total} ({percent}%){COLORS.reset}")
    save_results(target_results_path, correct, wrong, wrong_nouns)
    db.save_db_session(db_path, mode, attempts, case=case)
    print(
        f"{COLORS.dark_gray}Results saved to '{target_results_path.name}' "
        f"and '{db_path.name}'.{COLORS.reset}"
    )


def run_quiz_session(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    cards: list[Flashcard],
    target_results_path: Path,
    db_path: Path,
    case_cfg: dict,
    mode: str = "standard",
    case: str = "nominativ",
) -> bool:
    """Executes a single quiz session and saves results. Returns False if user aborted."""
    if mode == "review":
        quiz_cards = get_review_cards(cards, db_path, Config.QUIZ_LENGTH, case=case)
    else:
        quiz_cards = random.sample(cards, min(Config.QUIZ_LENGTH, len(cards)))

    options = case_cfg["options"]
    labels = case_cfg["labels"]
    wrong_nouns: list[str] = []
    attempts: list[tuple[str, str, str, int, str]] = []
    user_quit = False

    print(
        f"\n{COLORS.cyan}=== German Article Quiz ({case_cfg['name']}"
        f"{' - Review' if mode == 'review' else ''}, "
        f"{len(quiz_cards)} questions) ==={COLORS.reset}"
    )
    prompt_hint = "/".join(str(i) for i in range(1, len(labels) + 1))
    print(
        f"{COLORS.dark_gray}Select {prompt_hint} "
        f"(or type article). Enter 'q' to quit.{COLORS.reset}\n"
    )

    try:
        for idx, card in enumerate(quiz_cards, start=1):
            chosen = _prompt_card_choice(card, idx, len(quiz_cards), options, labels)
            if chosen is None:
                user_quit = True
                break

            if chosen == card.article:
                attempts.append(
                    (card.noun, card.article, chosen, 1, Config.current_timestamp())
                )
                print(f"{COLORS.green}Correct! ({card.article} {card.noun}){COLORS.reset}\n")
            else:
                wrong_nouns.append(card.noun)
                attempts.append(
                    (card.noun, card.article, chosen, 0, Config.current_timestamp())
                )
                print(
                    f"{COLORS.red}Wrong! The correct article is: "
                    f"{card.article} ({card.article} {card.noun}){COLORS.reset}\n"
                )
    except (KeyboardInterrupt, EOFError):
        print()
        user_quit = True

    if attempts:
        _record_quiz_summary(
            target_results_path, db_path, mode, attempts, wrong_nouns, case=case
        )

    return not user_quit


def _sync_database(
    db_path: Path, results_path: Path, cards: list[Flashcard], case: str = "nominativ"
) -> None:
    """Initializes the database and imports any pending results from results.txt."""
    db.init_db(db_path, case=case)
    noun_to_article = {card.noun: card.article for card in cards}
    migrated = db.migrate_results_txt(db_path, results_path, noun_to_article, case=case)
    if migrated > 0:
        print(
            f"{COLORS.dark_gray}Migrated {migrated} past session(s) from "
            f"'{results_path.name}' into '{db_path.name}' ({case}).{COLORS.reset}"
        )


def prompt_main_menu() -> str | None:
    """Prompts the user to choose an action from the top-level menu."""
    menu_actions = {
        "1": "case:nominativ",
        "nominativ": "case:nominativ",
        "2": "case:akkusativ",
        "akkusativ": "case:akkusativ",
        "3": "case:dativ",
        "dativ": "case:dativ",
        "4": "review",
        "review": "review",
        "review quiz": "review",
        "review:nominativ": "review:nominativ",
        "review nominativ": "review:nominativ",
        "review:akkusativ": "review:akkusativ",
        "review akkusativ": "review:akkusativ",
        "review:dativ": "review:dativ",
        "review dativ": "review:dativ",
        "5": "stats",
        "stats": "stats",
        "view stats": "stats",
    }
    while True:
        print(f"\n{COLORS.cyan}=== German Grammar Assistant ==={COLORS.reset}")
        print("  1. Nominativ Quiz (der / die / das)")
        print("  2. Akkusativ Quiz (den / die / das)")
        print("  3. Dativ Quiz (dem / der / den)")
        print("  4. Review Quiz (Struggling Nouns)")
        print("  5. View Stats (KPIs)")
        print("  6. Exit")
        try:
            choice = input("Choice: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            return None

        if choice in menu_actions:
            return menu_actions[choice]
        if choice in {"6", "q", "quit", "exit"}:
            return None
        print(f"{COLORS.yellow}Please enter 1, 2, 3, 4, 5, or 6.{COLORS.reset}")


def _sync_all_cases(base_dir: Path, db_path: Path | None = None) -> None:
    """Syncs pending results logs into SQLite for all configured quiz cases."""
    target_db = db_path if db_path is not None else base_dir / Config.DEFAULT_DB_FILE
    for case_key, cfg in Config.CASE_CONFIGS.items():
        vocab_path = base_dir / cfg["vocab_file"]
        results_path = base_dir / cfg["results_file"]
        cards = load_cards(vocab_path)
        if cards:
            _sync_database(target_db, results_path, cards, case=case_key)


def _show_review_interactive(base_dir: Path, db_path: Path | None = None) -> None:
    """Displays review menu to select which grammatical case to practice."""
    target_db = db_path if db_path is not None else base_dir / Config.DEFAULT_DB_FILE
    _sync_all_cases(base_dir, target_db)
    case_keys = list(Config.CASE_CONFIGS.keys())

    while True:
        print(f"\n{COLORS.cyan}=== Review Quiz: Select Case ==={COLORS.reset}")
        for idx, key in enumerate(case_keys, start=1):
            cfg = Config.CASE_CONFIGS[key]
            troubled = db.get_troubled_nouns(target_db, count=Config.QUIZ_LENGTH, case=key)
            t_count = len(troubled)
            status = (
                f"({t_count} troubled noun{'s' if t_count != 1 else ''})"
                if t_count
                else "(no troubled nouns)"
            )
            print(f"  {idx}. {cfg['name']} {COLORS.dark_gray}{status}{COLORS.reset}")
        print(f"  {len(case_keys) + 1}. Back to Main Menu")

        try:
            choice = input("Choice: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if choice in {str(len(case_keys) + 1), "q", "quit", "exit", "", "back"}:
            break

        selected_key = next(
            (key for idx, key in enumerate(case_keys, start=1)
             if choice in {str(idx), key, Config.CASE_CONFIGS[key]["name"].lower()}),
            None,
        )
        if selected_key is not None:
            cfg = Config.CASE_CONFIGS[selected_key]
            case_file = base_dir / cfg["vocab_file"]
            case_results = base_dir / cfg["results_file"]
            start_article_quiz(case_file, case_results, target_db, mode="review", case=selected_key)
            break
        print(f"{COLORS.yellow}Invalid option. Please choose 1-{len(case_keys) + 1}.{COLORS.reset}")


def _show_stats_interactive(base_dir: Path, db_path: Path | None = None) -> None:
    """Displays multi-quiz KPI overview and allows inspecting case-specific details."""
    target_db = db_path if db_path is not None else base_dir / Config.DEFAULT_DB_FILE
    _sync_all_cases(base_dir, target_db)
    case_keys = list(Config.CASE_CONFIGS.keys())

    while True:
        summaries = [
            (
                Config.CASE_CONFIGS[key]["name"],
                *db.get_session_summary(target_db, case=key),
            )
            for key in case_keys
        ]
        db.display_overview(summaries)
        print("Select a quiz to view detailed breakdown:")
        for idx, key in enumerate(case_keys, start=1):
            print(f"  {idx}. {Config.CASE_CONFIGS[key]['name']}")
        print(f"  {len(case_keys) + 1}. Back to Main Menu")

        try:
            choice = input("Choice: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if choice in {str(len(case_keys) + 1), "q", "quit", "exit", "", "back"}:
            break

        selected_key = None
        for idx, key in enumerate(case_keys, start=1):
            if choice in {str(idx), key, Config.CASE_CONFIGS[key]["name"].lower()}:
                selected_key = key
                break

        if selected_key is not None:
            cfg = Config.CASE_CONFIGS[selected_key]
            db.display_kpis(target_db, title=cfg["name"], case=selected_key)
        else:
            print(
                f"{COLORS.yellow}Invalid option. "
                f"Please choose 1-{len(case_keys) + 1}.{COLORS.reset}"
            )


def _run_stats_cli(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    base_dir: Path,
    file_path: Path,
    target_db_path: Path,
    target_results_path: Path,
    case_name: str | None,
    case_key: str | None,
) -> None:
    """Handles --stats flag reporting for CLI invocation."""
    if case_name is not None and case_key is not None:
        cards = load_cards(file_path)
        if cards:
            _sync_database(target_db_path, target_results_path, cards, case=case_key)
        db.display_kpis(target_db_path, title=case_name, case=case_key)
        return

    _sync_all_cases(base_dir, target_db_path)
    summaries = [
        (cfg["name"], *db.get_session_summary(target_db_path, case=k))
        for k, cfg in Config.CASE_CONFIGS.items()
    ]
    db.display_overview(summaries)
    for k, cfg in Config.CASE_CONFIGS.items():
        db.display_kpis(target_db_path, title=cfg["name"], case=k)


def run_interactive_menu(
    file_path: Path, results_path: Path, db_path: Path  # pylint: disable=unused-argument
) -> None:
    """Runs the interactive top-level menu loop."""
    base_dir = file_path.parent
    while True:
        choice = prompt_main_menu()
        if choice is None:
            break
        if choice == "stats":
            _show_stats_interactive(base_dir, db_path)
        elif choice == "review":
            _show_review_interactive(base_dir, db_path)
        elif choice.startswith("review:"):
            selected_case = choice.split(":")[1]
            cfg = Config.CASE_CONFIGS[selected_case]
            case_file = base_dir / cfg["vocab_file"]
            case_results = base_dir / cfg["results_file"]
            start_article_quiz(
                case_file, case_results, db_path, mode="review", case=selected_case
            )
        elif choice.startswith("case:"):
            selected_case = choice.split(":")[1]
            cfg = Config.CASE_CONFIGS[selected_case]
            case_file = base_dir / cfg["vocab_file"]
            case_results = base_dir / cfg["results_file"]
            start_article_quiz(
                case_file, case_results, db_path, mode="standard", case=selected_case
            )


def start_article_quiz(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    file_path: Path,
    results_path: Path | None = None,
    db_path: Path | None = None,
    mode: str = "standard",
    case: str = "nominativ",
) -> None:
    """Runs the interactive German article quiz with replay prompting."""

    cards = load_cards(file_path)
    if not cards:
        return

    case_cfg = Config.CASE_CONFIGS.get(case, Config.CASE_CONFIGS["nominativ"])
    target_results_path = (
        results_path if results_path is not None else file_path.parent / case_cfg["results_file"]
    )
    target_db_path = (
        db_path if db_path is not None else file_path.parent / Config.DEFAULT_DB_FILE
    )

    _sync_database(target_db_path, target_results_path, cards, case=case)

    while True:
        completed_normally = run_quiz_session(
            cards, target_results_path, target_db_path, case_cfg, mode, case=case
        )
        if not completed_normally:
            break
        if not ask_play_again():
            break


def main() -> None:
    """Parses command-line arguments and starts the article quiz or KPI viewer."""
    parser = argparse.ArgumentParser(
        description="Runs an interactive German article flashcard quiz with KPI tracking."
    )
    parser.add_argument(
        "file_path",
        nargs="?",
        default=None,
        type=Path,
        help="Path to the vocabulary file (defaults to case-appropriate file).",
    )
    parser.add_argument(
        "--case",
        choices=["nominativ", "akkusativ", "dativ"],
        default=None,
        help="Grammatical case for the quiz (default: nominativ for quiz, all for stats).",
    )
    parser.add_argument(
        "--mode",
        choices=["standard", "review"],
        default=None,
        help="Quiz mode: 'standard' for random words or 'review' for struggling nouns.",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Shortcut to launch directly in review mode.",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Display performance KPIs and statistics from database, then exit.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Path to SQLite database (default: quiz_history.db in vocabulary directory).",
    )
    args = parser.parse_args()

    selected_case = args.case if args.case is not None else "nominativ"
    case_cfg = Config.CASE_CONFIGS[selected_case]
    base_dir = Path(__file__).resolve().parent
    file_path = (
        args.file_path
        if args.file_path is not None
        else base_dir / case_cfg["vocab_file"]
    )

    target_db_path = (
        args.db_path
        if args.db_path is not None
        else base_dir / Config.DEFAULT_DB_FILE
    )
    target_results_path = file_path.parent / case_cfg["results_file"]

    if args.stats:
        case_name = case_cfg["name"] if args.case is not None else None
        case_key = selected_case if args.case is not None else None
        _run_stats_cli(
            base_dir, file_path, target_db_path, target_results_path, case_name, case_key
        )
        return

    if args.review or args.mode is not None:
        selected_mode = "review" if (args.review or args.mode == "review") else "standard"
        start_article_quiz(
            file_path=file_path,
            results_path=target_results_path,
            db_path=target_db_path,
            mode=selected_mode,
            case=selected_case,
        )
        return

    run_interactive_menu(file_path, target_results_path, target_db_path)


if __name__ == "__main__":
    main()
