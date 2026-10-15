"""Interactive German article flashcard quiz CLI application."""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import random
import sys

from config import Config
import db

COLORS = Config.COLORS


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
            parts = [part.strip() for part in line.split(";")]
            if len(parts) < 3 or not all(parts[:3]):
                continue
            cards.append(
                Flashcard(
                    article=parts[0].lower(),
                    noun=parts[1],
                    translation=parts[2],
                )
            )
    return cards


def save_results(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    results_path: Path,
    correct: int,
    wrong: int,
    wrong_nouns: list[str],
    right_nouns: list[str] | None = None,
    token: str = "",
) -> None:
    """Appends quiz results to a results file for trend and progress reporting."""
    record = {
        "date": Config.current_timestamp(),
        "token": token,
        "total": correct + wrong,
        "right": correct,
        "wrong": wrong,
        "right_nouns": right_nouns if right_nouns is not None else [],
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
    case: str = "nominativ",
    token: str = "",
) -> None:
    """Calculates and prints final score, then persists session to disk and database."""
    total = len(attempts)
    correct = sum(is_corr for _, _, _, is_corr, _ in attempts)
    wrong = total - correct
    right_nouns = [noun for noun, _, _, is_corr, _ in attempts if is_corr]
    wrong_nouns = [noun for noun, _, _, is_corr, _ in attempts if not is_corr]
    percent = round((correct / total) * 100)
    saved_token = db.save_db_session(db_path, mode, attempts, case=case, token=token or None)
    save_results(
        target_results_path,
        correct,
        wrong,
        wrong_nouns,
        right_nouns=right_nouns,
        token=saved_token,
    )
    print(
        f"\n{COLORS.cyan}Quiz finished! Score: {correct} / {total} ({percent}%) "
        f"| Token: {COLORS.yellow}{saved_token}{COLORS.reset}"
    )
    print(
        f"{COLORS.dark_gray}Results saved to '{target_results_path.name}' "
        f"and '{db_path.name}' (retake with token '{saved_token}').{COLORS.reset}"
    )


def run_quiz_session(
    cards: list[Flashcard],
    target_results_path: Path,
    db_path: Path,
    mode: str = "standard",
    case: str = "nominativ",
) -> bool:
    """Executes a single quiz session and saves results. Returns False if user aborted."""
    case_cfg = Config.CASE_CONFIGS.get(case, Config.CASE_CONFIGS["nominativ"])
    if mode == "review":
        quiz_cards = get_review_cards(cards, db_path, Config.QUIZ_LENGTH, case=case)
    elif mode.startswith("retake"):
        quiz_cards = random.sample(cards, len(cards))
    else:
        quiz_cards = random.sample(cards, min(Config.QUIZ_LENGTH, len(cards)))

    token = db.generate_unique_token(db_path)
    attempts: list[tuple[str, str, str, int, str]] = []
    user_quit = False

    print(
        f"\n{COLORS.cyan}=== German Article Quiz ({case_cfg['name']}"
        f"{' - Review' if mode == 'review' else ''}, "
        f"{len(quiz_cards)} questions) [Token: {token}] ==={COLORS.reset}"
    )
    print(
        f"{COLORS.dark_gray}Select "
        f"{'/'.join(str(i) for i in range(1, len(case_cfg['labels']) + 1))} "
        f"(or type article). Enter 'q' to quit.{COLORS.reset}\n"
    )

    try:
        for idx, card in enumerate(quiz_cards, start=1):
            chosen = _prompt_card_choice(
                card, idx, len(quiz_cards), case_cfg["options"], case_cfg["labels"]
            )
            if chosen is None:
                user_quit = True
                break

            is_correct = int(chosen == card.article)
            attempts.append(
                (card.noun, card.article, chosen, is_correct, Config.current_timestamp())
            )
            if is_correct:
                print(f"{COLORS.green}Correct! ({card.article} {card.noun}){COLORS.reset}\n")
            else:
                print(
                    f"{COLORS.red}Wrong! The correct article is: "
                    f"{card.article} ({card.article} {card.noun}){COLORS.reset}\n"
                )
    except (KeyboardInterrupt, EOFError):
        print()
        user_quit = True

    if attempts:
        _record_quiz_summary(
            target_results_path, db_path, mode, attempts, case=case, token=token
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
        "5": "sessions",
        "sessions": "sessions",
        "view sessions": "sessions",
        "6": "retake",
        "retake": "retake",
        "retake quiz": "retake",
        "7": "stats",
        "stats": "stats",
        "view stats": "stats",
    }
    while True:
        print(f"\n{COLORS.cyan}=== German Grammar Assistant ==={COLORS.reset}")
        print("  1. Nominativ Quiz (der / die / das)")
        print("  2. Akkusativ Quiz (den / die / das)")
        print("  3. Dativ Quiz (dem / der / den)")
        print("  4. Review Quiz (Struggling Nouns)")
        print("  5. View Sessions (History & Retake)")
        print("  6. Retake Quiz (by Token)")
        print("  7. View Stats (KPIs)")
        print("  8. Exit")
        try:
            choice = input("Choice: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            return None

        if choice in menu_actions:
            return menu_actions[choice]
        if choice.startswith(("retake:", "retake ")):
            token_arg = choice.split(":", 1)[1] if ":" in choice else choice.split(None, 1)[1]
            return f"retake:{token_arg.strip()}"
        if choice in {"8", "q", "quit", "exit"}:
            return None
        print(f"{COLORS.yellow}Please enter 1-8.{COLORS.reset}")


def _sync_all_cases(base_dir: Path, db_path: Path | None = None) -> None:
    """Syncs pending results logs into SQLite for all configured quiz cases."""
    target_db = db_path if db_path is not None else base_dir / Config.DEFAULT_DB_FILE
    for case_key, cfg in Config.CASE_CONFIGS.items():
        vocab_path = base_dir / cfg["vocab_file"]
        results_path = base_dir / cfg["results_file"]
        cards = load_cards(vocab_path)
        if cards:
            _sync_database(target_db, results_path, cards, case=case_key)


def _resolve_case_choice(choice: str, case_keys: list[str]) -> str | None:
    """Maps a 1-based numeric index, case key, or case display name to a case key."""
    return next(
        (
            key
            for idx, key in enumerate(case_keys, start=1)
            if choice in {str(idx), key, Config.CASE_CONFIGS[key]["name"].lower()}
        ),
        None,
    )


def _launch_case_quiz(
    base_dir: Path, db_path: Path, case: str, mode: str = "standard"
) -> None:
    """Resolves vocabulary and results paths for a case and starts a quiz."""
    cfg = Config.CASE_CONFIGS[case]
    start_article_quiz(
        file_path=base_dir / cfg["vocab_file"],
        results_path=base_dir / cfg["results_file"],
        db_path=db_path,
        mode=mode,
        case=case,
    )


def _retake_by_token(base_dir: Path, db_path: Path, token: str) -> bool:
    """Looks up a quiz session by its 4-character token and launches a retake."""
    clean_token = token.strip().upper()
    _sync_all_cases(base_dir, db_path)
    match = db.get_quiz_by_token(db_path, clean_token)
    if match is None:
        print(f"{COLORS.red}No quiz session found with token '{clean_token}'.{COLORS.reset}")
        return False

    case_key, nouns = match
    cfg = Config.CASE_CONFIGS[case_key]
    vocab_path = base_dir / cfg["vocab_file"]
    all_cards = load_cards(vocab_path)
    cards_by_noun = {card.noun: card for card in all_cards}
    selected_cards = [cards_by_noun[n] for n in nouns if n in cards_by_noun]
    if not selected_cards:
        print(
            f"{COLORS.red}Could not match nouns for token '{clean_token}' "
            f"in '{vocab_path.name}'.{COLORS.reset}"
        )
        return False

    print(
        f"{COLORS.cyan}Retaking {cfg['name']} quiz from token "
        f"'{clean_token}' ({len(selected_cards)} noun(s)).{COLORS.reset}"
    )
    start_article_quiz(
        file_path=vocab_path,
        results_path=base_dir / cfg["results_file"],
        db_path=db_path,
        mode=f"retake:{clean_token}",
        case=case_key,
        cards_override=selected_cards,
    )
    return True


def _prompt_retake_interactive(base_dir: Path, db_path: Path | None = None) -> None:
    """Prompts the user for a 4-character quiz token to retake."""
    target_db = db_path if db_path is not None else base_dir / Config.DEFAULT_DB_FILE
    while True:
        try:
            token = input(
                "\nEnter 4-character quiz token to retake (or 'q' to go back): "
            ).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if token.lower() in {"", "q", "quit", "exit", "back"}:
            break

        if _retake_by_token(base_dir, target_db, token):
            break


def _show_sessions_interactive(base_dir: Path, db_path: Path | None = None) -> None:
    """Displays recorded quiz sessions and optionally allows retaking one by token."""
    target_db = db_path if db_path is not None else base_dir / Config.DEFAULT_DB_FILE
    _sync_all_cases(base_dir, target_db)
    sessions = db.display_sessions(target_db)
    if not sessions:
        return

    while True:
        try:
            token = input(
                "Enter a 4-character token to retake that quiz (or press Enter to go back): "
            ).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if token.lower() in {"", "q", "quit", "exit", "back"}:
            break

        if _retake_by_token(base_dir, target_db, token):
            break


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

        selected_key = _resolve_case_choice(choice, case_keys)
        if selected_key is not None:
            _launch_case_quiz(base_dir, target_db, selected_key, mode="review")
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

        selected_key = _resolve_case_choice(choice, case_keys)
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


def run_interactive_menu(file_path: Path, db_path: Path) -> None:
    """Runs the interactive top-level menu loop."""
    base_dir = file_path.parent
    while True:
        choice = prompt_main_menu()
        if choice is None:
            break
        if choice == "stats":
            _show_stats_interactive(base_dir, db_path)
        elif choice == "sessions":
            _show_sessions_interactive(base_dir, db_path)
        elif choice == "retake":
            _prompt_retake_interactive(base_dir, db_path)
        elif choice.startswith("retake:"):
            _retake_by_token(base_dir, db_path, choice.split(":", 1)[1])
        elif choice == "review":
            _show_review_interactive(base_dir, db_path)
        elif ":" in choice:
            prefix, selected_case = choice.split(":", 1)
            mode = "review" if prefix == "review" else "standard"
            _launch_case_quiz(base_dir, db_path, selected_case, mode=mode)


def start_article_quiz(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    file_path: Path,
    results_path: Path | None = None,
    db_path: Path | None = None,
    mode: str = "standard",
    case: str = "nominativ",
    cards_override: list[Flashcard] | None = None,
) -> None:
    """Runs the interactive German article quiz with replay prompting."""
    all_cards = load_cards(file_path)
    if not all_cards:
        return

    case_cfg = Config.CASE_CONFIGS.get(case, Config.CASE_CONFIGS["nominativ"])
    target_results_path = (
        results_path if results_path is not None else file_path.parent / case_cfg["results_file"]
    )
    target_db_path = (
        db_path if db_path is not None else file_path.parent / Config.DEFAULT_DB_FILE
    )

    _sync_database(target_db_path, target_results_path, all_cards, case=case)
    active_cards = cards_override if cards_override is not None else all_cards

    while True:
        completed_normally = run_quiz_session(
            active_cards, target_results_path, target_db_path, mode, case=case
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
        "--retake",
        metavar="TOKEN",
        default=None,
        help="Retake a specific quiz session using its 4-character alphanumeric token.",
    )
    parser.add_argument(
        "--sessions",
        action="store_true",
        help="Display recorded quiz sessions and their 4-character tokens, then exit.",
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

    if args.sessions:
        _sync_all_cases(base_dir, target_db_path)
        db.display_sessions(target_db_path, case=args.case)
        return

    if args.retake:
        _retake_by_token(base_dir, target_db_path, args.retake)
        return

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

    run_interactive_menu(file_path, target_db_path)


if __name__ == "__main__":
    main()
