"""Database operations and KPI reporting for German Article Assistant."""
from __future__ import annotations
import json
from pathlib import Path
import random
import sqlite3
import string

from config import Config

COLORS = Config.COLORS
TOKEN_CHARS = string.ascii_uppercase + string.digits
TOKEN_LENGTH = 4


def _get_table_names(case: str = "nominativ") -> tuple[str, str]:
    """Returns sanitized (sessions_table, attempts_table) for a given grammatical case."""
    clean_case = case.strip().lower()
    if clean_case not in Config.CASE_CONFIGS:
        clean_case = "nominativ"
    return f"{clean_case}_quiz_sessions", f"{clean_case}_card_attempts"


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    """Checks whether a table exists in the SQLite database."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _has_token_column(cursor: sqlite3.Cursor, sessions_table: str) -> bool:
    """Checks whether a sessions table has the token column."""
    if not _table_exists(cursor, sessions_table):
        return False
    cursor.execute(f"PRAGMA table_info({sessions_table})")
    return "token" in {row[1] for row in cursor.fetchall()}


def _generate_token_with_cursor(cursor: sqlite3.Cursor) -> str:
    """Generates a unique 4-character alphanumeric token using an active cursor."""
    existing: set[str] = set()
    for case_key in Config.CASE_CONFIGS:
        sessions_table, _ = _get_table_names(case_key)
        if _has_token_column(cursor, sessions_table):
            cursor.execute(f"SELECT UPPER(token) FROM {sessions_table}")
            existing.update(row[0] for row in cursor.fetchall() if row[0])

    while True:
        candidate = "".join(random.choices(TOKEN_CHARS, k=TOKEN_LENGTH))
        if candidate not in existing:
            return candidate


def generate_unique_token(db_path: Path) -> str:
    """Generates a 4-character alphanumeric token unique across all quiz sessions."""
    if not db_path.is_file():
        return "".join(random.choices(TOKEN_CHARS, k=TOKEN_LENGTH))
    with sqlite3.connect(db_path) as conn:
        return _generate_token_with_cursor(conn.cursor())


def init_db(db_path: Path, case: str = "nominativ") -> None:
    """Initializes SQLite database schema for sessions, card attempts, and metadata."""
    sessions_table, attempts_table = _get_table_names(case)
    idx_name = f"idx_{attempts_table}_noun"

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        if case == "nominativ":
            for old_table, new_table in (
                ("quiz_sessions", sessions_table),
                ("card_attempts", attempts_table),
            ):
                if _table_exists(cursor, old_table) and not _table_exists(cursor, new_table):
                    cursor.execute(f"ALTER TABLE {old_table} RENAME TO {new_table}")

        if _table_exists(cursor, sessions_table) and not _has_token_column(cursor, sessions_table):
            cursor.execute(f"DROP TABLE IF EXISTS {attempts_table}")
            cursor.execute(f"DROP TABLE IF EXISTS {sessions_table}")
            if _table_exists(cursor, "meta"):
                cursor.execute(
                    "DELETE FROM meta WHERE key IN (?, 'results_txt_migrated')",
                    (f"results_txt_migrated_{case}",),
                )

        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {sessions_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                total INTEGER NOT NULL,
                correct INTEGER NOT NULL,
                quiz_mode TEXT NOT NULL DEFAULT 'standard'
            )
            """
        )
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {attempts_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                noun TEXT NOT NULL,
                expected_article TEXT NOT NULL,
                user_answer TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                answered_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES {sessions_table} (id)
            )
            """
        )
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {attempts_table}(noun)"
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            f"""
            DELETE FROM {attempts_table}
            WHERE session_id IN (
                SELECT s.id FROM {sessions_table} s
                WHERE s.quiz_mode = 'migrated'
                  AND (
                      SELECT COUNT(*) FROM {attempts_table} a
                      WHERE a.session_id = s.id
                  ) < s.total
            )
            """
        )
        cursor.execute(
            f"""
            DELETE FROM {sessions_table}
            WHERE quiz_mode = 'migrated'
              AND (
                  SELECT COUNT(*) FROM {attempts_table} a
                  WHERE a.session_id = {sessions_table}.id
              ) < total
            """
        )
        conn.commit()


def _insert_migrated_record(
    cursor: sqlite3.Cursor,
    data: dict,
    noun_to_article: dict[str, str],
    case: str = "nominativ",
) -> None:
    """Inserts a single migrated legacy session record into the database."""
    sessions_table, attempts_table = _get_table_names(case)
    token = str(data.get("token") or _generate_token_with_cursor(cursor)).upper()
    date_str = str(data.get("date", Config.current_timestamp()))
    total = int(data.get("total", 0))
    correct = int(data.get("right", 0))
    right_nouns = data.get("right_nouns", [])
    wrong_nouns = data.get("wrong_nouns", [])

    cursor.execute(
        f"""
        INSERT INTO {sessions_table} (token, created_at, total, correct, quiz_mode)
        VALUES (?, ?, ?, ?, 'migrated')
        """,
        (token, date_str, total, correct),
    )
    session_id = cursor.lastrowid

    if session_id is not None and (right_nouns or wrong_nouns):
        attempts = [
            (
                session_id,
                noun,
                noun_to_article.get(noun, ""),
                noun_to_article.get(noun, ""),
                1,
                date_str,
            )
            for noun in right_nouns
        ] + [
            (session_id, noun, noun_to_article.get(noun, ""), "", 0, date_str)
            for noun in wrong_nouns
        ]
        cursor.executemany(
            f"""
            INSERT INTO {attempts_table} (
                session_id, noun, expected_article, user_answer,
                is_correct, answered_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            attempts,
        )


def migrate_results_txt(
    db_path: Path,
    results_path: Path,
    noun_to_article: dict[str, str],
    case: str = "nominativ",
) -> int:
    """Migrates legacy results.txt JSON lines into the SQLite database."""
    if not results_path.is_file():
        return 0

    meta_key = f"results_txt_migrated_{case}"
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value FROM meta WHERE key = ? OR "
            "(key = 'results_txt_migrated' AND ? = 'nominativ')",
            (meta_key, case),
        )
        if cursor.fetchone():
            return 0

        migrated_sessions = 0

        with results_path.open("r", encoding="utf-8") as file:
            for line in file:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                _insert_migrated_record(cursor, data, noun_to_article, case=case)
                migrated_sessions += 1

        cursor.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, '1')",
            (meta_key,),
        )
        conn.commit()

    return migrated_sessions


def save_db_session(
    db_path: Path,
    mode: str,
    attempts: list[tuple[str, str, str, int, str]],
    case: str = "nominativ",
    token: str | None = None,
) -> str:
    """Records full quiz session summary and individual card attempts in SQLite."""
    if not attempts:
        return ""

    sessions_table, attempts_table = _get_table_names(case)
    total = len(attempts)
    correct = sum(is_corr for _, _, _, is_corr, _ in attempts)
    created_at = Config.current_timestamp()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        session_token = (token or _generate_token_with_cursor(cursor)).upper()
        cursor.execute(
            f"""
            INSERT INTO {sessions_table} (token, created_at, total, correct, quiz_mode)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_token, created_at, total, correct, mode),
        )
        session_id = cursor.lastrowid
        if session_id is not None:
            cursor.executemany(
                f"""
                INSERT INTO {attempts_table} (
                    session_id, noun, expected_article, user_answer, is_correct, answered_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(session_id, *attempt) for attempt in attempts],
            )
        conn.commit()
    return session_token


def get_troubled_nouns(
    db_path: Path,
    count: int = 20,
    min_accuracy: float = 0.8,
    streak_target: int = 2,
    case: str = "nominativ",
) -> list[str]:  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Retrieves nouns with past errors, graduating words with sufficient accuracy or streak."""
    if not db_path.is_file():
        return []

    _, attempts_table = _get_table_names(case)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        if not _table_exists(cursor, attempts_table):
            return []

        cursor.execute(
            f"""
            WITH noun_stats AS (
                SELECT noun,
                       COUNT(*) AS attempts,
                       SUM(is_correct) AS correct_count,
                       (COUNT(*) - SUM(is_correct)) AS mistakes,
                       (CAST(SUM(is_correct) AS FLOAT) / COUNT(*)) AS success_rate,
                       COUNT(CASE WHEN id > last_error_id THEN 1 END) AS current_streak
                FROM (
                    SELECT id, noun, is_correct,
                           MAX(CASE WHEN is_correct = 0 THEN id END)
                               OVER (PARTITION BY noun) AS last_error_id
                    FROM {attempts_table}
                )
                GROUP BY noun
            )
            SELECT noun
            FROM noun_stats
            WHERE mistakes > 0
              AND success_rate < ?
              AND current_streak < ?
            ORDER BY success_rate ASC, mistakes DESC, attempts DESC
            LIMIT ?
            """,
            (min_accuracy, streak_target, count),
        )
        return [row[0] for row in cursor.fetchall()]


def get_session_summary(db_path: Path, case: str = "nominativ") -> tuple[int, int, int]:
    """Returns (sessions_count, total_questions, total_correct) from quiz history."""
    if not db_path.is_file():
        return 0, 0, 0

    sessions_table, _ = _get_table_names(case)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        if not _table_exists(cursor, sessions_table):
            return 0, 0, 0

        cursor.execute(
            f"""
            SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
            FROM {sessions_table}
            """
        )
        row = cursor.fetchone()
        return (int(row[0]), int(row[1]), int(row[2])) if row else (0, 0, 0)


def display_overview(summaries: list[tuple[str, int, int, int]]) -> None:
    """Displays comparative KPI overview table across multiple quiz types."""
    print(f"\n{COLORS.cyan}=== Performance KPIs & Quiz Statistics Overview ==={COLORS.reset}")
    header = (
        f"{'Quiz / Case':<15} {'Sessions':>10} {'Answered':>10} "
        f"{'Correct':>10} {'Accuracy':>10}"
    )
    print(header)
    print("-" * len(header))

    total_sessions = 0
    total_qs = 0
    total_corr = 0

    for name, sessions, questions, correct in summaries:
        total_sessions += sessions
        total_qs += questions
        total_corr += correct
        acc_str = f"{(correct / questions) * 100:.1f}%" if questions > 0 else "N/A"
        print(f"{name:<15} {sessions:>10} {questions:>10} {correct:>10} {acc_str:>10}")

    print("-" * len(header))
    tot_acc_str = f"{(total_corr / total_qs) * 100:.1f}%" if total_qs > 0 else "N/A"
    print(f"{'Total':<15} {total_sessions:>10} {total_qs:>10} {total_corr:>10} {tot_acc_str:>10}\n")


def _display_article_stats(cursor: sqlite3.Cursor, attempts_table: str) -> None:
    """Prints accuracy stats grouped by German grammatical article."""
    cursor.execute(
        f"""
        SELECT expected_article, COUNT(*), SUM(is_correct)
        FROM {attempts_table}
        WHERE expected_article != ''
        GROUP BY expected_article
        ORDER BY expected_article
        """
    )
    article_rows = cursor.fetchall()
    if article_rows:
        print(f"\n{COLORS.cyan}--- Accuracy by Article ---{COLORS.reset}")
        for art, atts, corr in article_rows:
            acc = round((corr / atts) * 100, 1) if atts else 0.0
            print(f"  {art:<4}: {acc:>5.1f}% ({corr}/{atts})")


def _display_troubled_words(cursor: sqlite3.Cursor, attempts_table: str) -> None:
    """Prints weakest nouns and frequent article confusion patterns."""
    cursor.execute(
        f"""
        SELECT noun, expected_article,
               SUM(is_correct) AS total_corr,
               (COUNT(*) - SUM(is_correct)) AS mistakes,
               ROUND((CAST(SUM(is_correct) AS FLOAT) / COUNT(*)) * 100, 1) AS acc
        FROM {attempts_table}
        GROUP BY noun
        HAVING mistakes > 0
        ORDER BY acc ASC, mistakes DESC
        LIMIT 10
        """
    )
    struggling_rows = cursor.fetchall()
    if struggling_rows:
        print(f"\n{COLORS.cyan}--- Top Struggling Nouns ---{COLORS.reset}")
        for noun, exp, corr, mistakes, acc in struggling_rows:
            art_label = f" ({exp})" if exp else ""
            print(
                f"  {COLORS.yellow}{noun}{art_label}{COLORS.reset}: "
                f"{acc}% accuracy ({corr} correct, {COLORS.red}{mistakes} mistakes{COLORS.reset})"
            )

    cursor.execute(
        f"""
        SELECT expected_article, user_answer, COUNT(*) AS err_count
        FROM {attempts_table}
        WHERE is_correct = 0
          AND expected_article != ''
          AND user_answer != ''
        GROUP BY expected_article, user_answer
        ORDER BY err_count DESC
        LIMIT 5
        """
    )
    confusion_rows = cursor.fetchall()
    if confusion_rows:
        print(f"\n{COLORS.cyan}--- Top Article Confusions ---{COLORS.reset}")
        for exp, ans, count in confusion_rows:
            print(f"  Expected '{exp}' -> answered '{ans}': {count} time(s)")


def display_kpis(
    db_path: Path, title: str | None = None, case: str = "nominativ"
) -> None:
    """Displays key performance indicators and error diagnostics from SQLite history."""
    if not db_path.is_file():
        label = f" for '{title}'" if title else ""
        print(
            f"{COLORS.yellow}No database file found{label} at '{db_path.name}'. "
            f"Take a quiz first!{COLORS.reset}"
        )
        return

    sessions_count, total_qs, total_correct = get_session_summary(db_path, case=case)
    if sessions_count == 0:
        label = f" for {title}" if title else ""
        print(
            f"{COLORS.yellow}No quiz sessions recorded yet{label}. "
            f"Complete a quiz to view KPIs!{COLORS.reset}"
        )
        return

    overall_acc = round((total_correct / total_qs) * 100, 1) if total_qs else 0.0
    acc_color = COLORS.green if overall_acc >= 75 else COLORS.yellow
    header = (
        f"=== Performance KPIs & Quiz Statistics ({title}) ==="
        if title
        else "=== Performance KPIs & Quiz Statistics ==="
    )

    print(f"\n{COLORS.cyan}{header}{COLORS.reset}")
    print(f"Total Sessions:      {sessions_count}")
    print(f"Questions Answered:  {total_qs}")
    print(f"Correct Answers:     {total_correct}")
    print(f"Overall Accuracy:    {acc_color}{overall_acc}%{COLORS.reset}")

    _, attempts_table = _get_table_names(case)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        _display_article_stats(cursor, attempts_table)
        _display_troubled_words(cursor, attempts_table)
    print()


def get_all_sessions(
    db_path: Path, case: str | None = None, limit: int = 50
) -> list[tuple[str, str, str, str, int, int]]:
    """Retrieves recent quiz sessions as (token, created_at, case, mode, correct, total)."""
    if not db_path.is_file():
        return []

    cases = [case] if case in Config.CASE_CONFIGS else list(Config.CASE_CONFIGS.keys())
    rows: list[tuple[str, str, str, str, int, int]] = []

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for case_key in cases:
            sessions_table, _ = _get_table_names(case_key)
            if not _has_token_column(cursor, sessions_table):
                continue
            cursor.execute(
                f"""
                SELECT token, created_at, quiz_mode, correct, total
                FROM {sessions_table}
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows.extend(
                (str(r[0]), str(r[1]), case_key, str(r[2]), int(r[3]), int(r[4]))
                for r in cursor.fetchall()
            )

    rows.sort(key=lambda r: r[1], reverse=True)
    return rows[:limit]


def display_sessions(
    db_path: Path, case: str | None = None
) -> list[tuple[str, str, str, str, int, int]]:
    """Displays a table of recorded quiz sessions with their 4-char retake tokens."""
    sessions = get_all_sessions(db_path, case=case)
    if not sessions:
        print(
            f"\n{COLORS.yellow}No recorded quiz sessions found. "
            f"Complete a quiz first!{COLORS.reset}"
        )
        return []

    print(f"\n{COLORS.cyan}=== Recorded Quiz Sessions ==={COLORS.reset}")
    header = (
        f"{'Token':<8} {'Date':<21} {'Case':<12} "
        f"{'Mode':<14} {'Score':>9} {'Accuracy':>10}"
    )
    print(header)
    print("-" * len(header))

    for token, created_at, case_key, mode, correct, total in sessions:
        case_name = Config.CASE_CONFIGS.get(case_key, {}).get("name", case_key.capitalize())
        acc_str = f"{(correct / total) * 100:.1f}%" if total > 0 else "N/A"
        score_str = f"{correct}/{total}"
        print(
            f"{COLORS.yellow}{token:<8}{COLORS.reset} {created_at:<21} "
            f"{case_name:<12} {mode:<14} {score_str:>9} {acc_str:>10}"
        )
    print("-" * len(header) + "\n")
    return sessions


def get_quiz_by_token(db_path: Path, token: str) -> tuple[str, list[str]] | None:
    """Looks up a quiz session by its 4-character token and returns (case, nouns)."""
    clean_token = token.strip().upper()
    if not clean_token or not db_path.is_file():
        return None

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for case_key in Config.CASE_CONFIGS:
            sessions_table, attempts_table = _get_table_names(case_key)
            if not _has_token_column(cursor, sessions_table):
                continue
            cursor.execute(
                f"SELECT id FROM {sessions_table} WHERE UPPER(token) = ? ORDER BY id DESC LIMIT 1",
                (clean_token,),
            )
            row = cursor.fetchone()
            if row is not None and _table_exists(cursor, attempts_table):
                cursor.execute(
                    f"SELECT noun FROM {attempts_table} WHERE session_id = ? ORDER BY id ASC",
                    (row[0],),
                )
                nouns = [r[0] for r in cursor.fetchall()]
                if nouns:
                    return case_key, nouns
    return None
