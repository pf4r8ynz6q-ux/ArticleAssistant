# German Article Assistant

A command-line flashcard tool designed to help practice and master German noun articles across grammatical cases: **Nominativ** (`der`, `die`, `das`), **Akkusativ** (`den`, `die`, `das`), and **Dativ** (`dem`, `der`, `den`).

## Features

- **Multi-Case Practice**: Learn articles across Nominativ, Akkusativ, and Dativ with case-appropriate article options and plural forms.
- **Bite-sized Sessions**: Each quiz presents 20 randomized, non-repeating nouns from your vocabulary list.
- **Flexible Input**: Answer using quick number keys (`1`, `2`, `3`) or by typing the article directly.
- **Consolidated SQLite History**: All session summaries and granular question-by-question attempts are persisted into case-specific tables within a single `quiz_history.db`.
- **Targeted Review Mode**: Reinforce troubled words per case based on historical accuracy and error streaks, with automated graduation as proficiency improves.
- **Interactive Main Menu**: Launch without flags to access standard quizzes, review queues with active word counts, and comparative statistics.
- **In-Depth KPI Reporting**: View comparative cross-case overviews, article-level accuracy percentages, top troubled nouns, and frequent article confusion patterns.
- **Automatic Legacy Migration**: Automatically detects and migrates legacy JSON-line results logs (`results.txt`, `results_akkusativ.txt`, `results_dativ.txt`) into SQLite.
- **Replay Option**: Prompt to instantly start another round or exit after viewing session totals.
- **Custom Vocabulary**: Supports custom semicolon-delimited flashcard files via command-line arguments.

## Requirements

- Python 3.8+ (standard library only, no external dependencies required)
- A terminal supporting ANSI color codes

## Getting Started

### 1. Run Interactive Menu (Default)

Launch the assistant with the default vocabulary and interactive menu:

```text
=== German Grammar Assistant ===
  1. Nominativ Quiz (der / die / das)
  2. Akkusativ Quiz (den / die / das)
  3. Dativ Quiz (dem / der / den)
  4. Review Quiz (Struggling Nouns)
  5. View Stats (KPIs)
  6. Exit
Choice:
```

Run via:

```bash
python article_assist.py
```

### 2. Run with a custom vocabulary file

Pass a path to any custom semicolon-delimited flashcard file:

```bash
python article_assist.py path/to/my_words.txt
```

## How to Play

When prompted with a noun and its translation:

```text
[1/20] Mann (man)
  1. Der
  2. Die
  3. Das
Choice: 
```

- Type `1`, `2`, or `3` (or type `der`, `die`, or `das`) and press **Enter**.
- Type `q`, `quit`, or `exit` at any time to exit the session early.
- If answered incorrectly, the correct article will be displayed and the noun will be recorded for post-quiz review.

## File Formats

### Vocabulary File (`articles.txt`)

Lines follow a semicolon-delimited format: `<article>;<noun>;<translation>`

```plaintext
der;Mann;man
die;Frau;woman
das;Kind;child
```

### Results Log (`results.txt`)

Each completed quiz appends a JSON line record:

```json
{"date": "2026-10-11 13:00:09", "total": 20, "right": 9, "wrong": 11, "wrong_nouns": ["Kuchen", "Woche", "Gegend"]}
```

> **Note**: `results.txt` is ignored by Git in `.gitignore` to avoid checking personal quiz history into source control.