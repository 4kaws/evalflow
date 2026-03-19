# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Evalflow is a terminal UI (built with [Textual](https://github.com/Textualize/textual)) for pulling Kaggle Community Benchmark output CSVs, merging them into two research-ready datasets (`evalflow_sft.csv` and `evalflow_preferences.csv`), and publishing them to Kaggle Datasets — all from a single app.

## Running the App

```bash
# Install dependencies (Python 3.12+)
pip install textual pandas python-dotenv kaggle

# Launch TUI (auto-runs setup wizard on first run if .env is missing)
python evalflow.py

# Skip the setup wizard
python evalflow.py --no-wizard

# Headless CI usage (pull + merge + publish without opening TUI)
python ci_runner.py --slug username/benchmark-name --dataset-slug my-results --dataset-title "My Results" --publish
```

## Configuration

Create a `.env` file (or let the setup wizard generate one):

```env
KAGGLE_USERNAME=your-username
KAGGLE_KEY=your-api-key
OUTPUT_DIR=outputs          # default
```

Full config is in [config.py](config.py) — loaded via `Config.load()` into a module-level singleton `config`. Views import `from config import config`.

## Architecture

### Entry Points
- **`evalflow.py`** — Textual `App` subclass (`EvalflowApp`). Composes a sidebar (`NavItem` widgets) + a `ContentSwitcher` holding all five views. Navigation is handled by `switch_view(view_id)` which also calls `on_activate()` on the view if defined.
- **`ci_runner.py`** — Headless alternative: discovers tasks, pulls CSVs, merges, optionally publishes. Shares `core/` logic with the TUI.
- **`setup_wizard.py`** — Separate Textual app run before `EvalflowApp` when `.env` is missing.

### Views (`views/`)
Each view is a Textual `Widget` subclass rendered in the `ContentSwitcher`:

| View file | Tab | Purpose |
|---|---|---|
| `pull_view.py` | 1 – Pull | Discovers all task notebooks under a benchmark slug via 3-strategy fallback, downloads output CSVs |
| `results_view.py` | 2 – Results | Browse pulled CSVs, filter by model/score |
| `leaderboard_view.py` | 3 – Leaderboard | Cross-model accuracy ranking with per-question pass/fail diff |
| `merge_view.py` | 4 – Merge | Calls `core/merger.py` to produce the two output CSVs |
| `publish_view.py` | 5 – Publish | Calls `core/uploader.py` to push to Kaggle Datasets |

### Core Logic (`core/`)
- **`merger.py`** — `merge_outputs(csv_paths, output_dir)` → `(sft_df, pref_df, stats)`. Validates CSVs against `REQUIRED_COLUMNS`, concatenates, deduplicates, builds Format A (SFT, one row per model response) and Format B (preference pairs, one row per question where at least one model passed and one failed).
- **`uploader.py`** — `upload_dataset(folder, is_update, log_cb)` → `UploadResult`. Wraps Kaggle SDK's `dataset_create_new` / `dataset_create_version`.

### Task Discovery (3-Strategy Fallback)
Both `pull_view.py` and `ci_runner.py` use the same pattern:
1. `kernels_list(parent=benchmark_slug)` — official parent/child API
2. `kernels_list(user=username, search=slug_name)` — name search fallback
3. Treat slug as single-task benchmark

Output CSVs are prefixed `<task-short-name>__<original-name>.csv` to avoid collisions in `outputs/`.

### Merge Output Schema
`evalflow_sft.csv` — columns defined by `SFT_COLUMNS` in `merger.py`. Key required source columns: `task_name`, `model_name`, `question`, `ground_truth`, `llm_response`, `score`.

`evalflow_preferences.csv` — columns defined by `PREF_COLUMNS`. Built from questions where at least one model passed (`score=1`) and one failed (`score=0`). Chosen = longest correct response; Rejected = shortest incorrect response.

## CI / GitHub Actions

`.github/workflows/evalflow_ci.yml` runs the full pipeline headlessly. Requires GitHub Secrets `KAGGLE_USERNAME` and `KAGGLE_KEY`. Trigger manually via Actions → Run workflow with inputs: `notebook_slug`, `dataset_slug`, `dataset_title`, `update_existing`.

## Notebook Template

`notebooks/notebook_template.ipynb` is the starting point for task authors. The fields to customize: `TASK_NAME`, `PROMPT_TEMPLATE`, `EVALUATION_DATA`, `CRITERIA`, and the `%choose` magic in the last cell.
