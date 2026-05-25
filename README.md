<div align="center">

```
███████╗██╗   ██╗ █████╗ ██╗     ███████╗██╗      ██████╗ ██╗    ██╗
██╔════╝██║   ██║██╔══██╗██║     ██╔════╝██║     ██╔═══██╗██║    ██║
█████╗  ╚██╗ ██╔╝███████║██║     █████╗  ██║     ██║   ██║██║ █╗ ██║
██╔══╝   ╚████╔╝ ██╔══██║██║     ██╔══╝  ██║     ██║   ██║██║███╗██║
███████╗  ╚██╔╝  ██║  ██║███████╗██║     ███████╗╚██████╔╝╚███╔███╔╝
╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝
```

</div>

A terminal UI for pulling Kaggle Community Benchmark results, merging them into
publication-ready datasets, and publishing them to Kaggle Datasets — all from the terminal.

You write your benchmark on Kaggle. Kaggle runs it against as many models as you want
for free. Evalflow handles everything after that: one slug, all tasks pulled at once,
two research-ready CSVs produced, published to Kaggle Datasets in one click.

The two datasets Evalflow produces are formats actively used in AI research and model training:

- **`evalflow_sft.csv`** — a Supervised Fine-Tuning (SFT) dataset. One row per model response,
  with the full conversation in chat format. Used to fine-tune language models on
  instruction-following by training them on correct responses.

- **`evalflow_preferences.csv`** — a preference dataset for RLHF / Direct Preference Optimization
  (DPO). One row per question where at least one model passed and one failed, pairing a chosen
  (correct) response against a rejected (incorrect) one. Used to align language models toward
  better answers without human labellers — the benchmark judge does the labelling automatically.

Both files are ready to load directly into training pipelines (Hugging Face `datasets`,
TRL, LLaMA-Factory, and similar frameworks) or to share publicly on Kaggle Datasets so
other researchers can build on your benchmark results.

---

## Workflow

```
Kaggle (browser)                              Evalflow (terminal)
─────────────────────────────────────         ──────────────────────────────────────
1. Write your task notebooks                  5. Pull
   One notebook per task.                        Paste your benchmark slug once.
                                                 Evalflow auto-discovers all tasks
2. Group them into a Benchmark                   and downloads every .run.json file.
   on kaggle.com/benchmarks
                                             6. Results
3. Click Add Models on the                       Browse pulled data, filter by
   Benchmark page to run across                  model and score.
   Claude, Gemini, Llama, DeepSeek
   (free, within quota)                      7. Leaderboard
                                                 Cross-model accuracy ranking with
4. Kaggle runs each task notebook                per-question score comparison.
   against every model and saves
   the results as .run.json files           8. Merge
                                                 Combines all outputs into two files:
                                                   evalflow_sft.csv
                                                   evalflow_preferences.csv

                                             9. Publish
                                                 Uploads both to Kaggle Datasets.
                                                 Re-publishing appends new data
                                                 and deduplicates automatically.

                                            10. Monitor (optional)
                                                 Add watchers for your benchmarks.
                                                 Evalflow checks daily for new tasks,
                                                 pulls them automatically, and
                                                 publishes the updated dataset —
                                                 with or without the TUI open.
```

---

## Installation

### Linux

```bash
# Python 3.12+ is required
python3 --version

git clone https://github.com/4kaws/evalflow.git
cd evalflow

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
python evalflow.py
```

---

### macOS

```bash
# Install Python 3.12+ via Homebrew if needed
brew install python@3.12

git clone https://github.com/4kaws/evalflow.git
cd evalflow

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
python evalflow.py
```

> **Terminal tip:** Evalflow works best in Terminal.app or iTerm2 with a font that
> supports Unicode block characters (most modern fonts do). If the logo looks broken,
> go to Terminal → Preferences → Profiles → Text and pick a font like
> **Menlo**, **JetBrains Mono**, or **Fira Code**.

---

### Windows (via WSL)

Evalflow requires a real Unix terminal — WSL (Windows Subsystem for Linux) provides that.

**1. Install WSL** (if not already installed — run in PowerShell as Administrator):

```powershell
wsl --install
```

Restart your machine when prompted. This installs Ubuntu by default.

**2. Open Ubuntu from the Start menu**, then inside WSL:

```bash
# Update packages and install Python 3.12+
sudo apt update && sudo apt upgrade -y
sudo apt install python3.12 python3.12-venv python3-pip git -y

# Clone Evalflow
git clone https://github.com/4kaws/evalflow.git
cd evalflow

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
python evalflow.py
```

> **Recommended terminal:** Use **Windows Terminal** (free from the Microsoft Store)
> for the best experience — it renders Unicode box-drawing characters and colours
> correctly. The default CMD/PowerShell window does not.

---

> **On subsequent runs** just activate the venv and launch:
> ```bash
> source venv/bin/activate   # Windows WSL / Linux / macOS
> python evalflow.py
> ```

---

## First Run

The setup wizard launches automatically on first run and collects:

- **Kaggle credentials** — username and legacy API key
  Get yours at: **kaggle.com → Settings → Account → Legacy API Credentials → Create Legacy API Key**
- **GitHub token and repo** — needed for the daily cloud schedule to sync your watcher config
  Create a fine-grained PAT at **github.com → Settings → Developer settings → Fine-grained tokens** with **Secrets: read & write** permission on your repo

You can also skip the wizard and create a `.env` file manually:

```env
KAGGLE_USERNAME=your-username
KAGGLE_KEY=your-legacy-api-key
GITHUB_TOKEN=your-github-pat
GITHUB_REPO=owner/repo
```

To re-open the wizard at any time, press `w` inside the TUI.

Credentials are saved to `.env` and persist between sessions. All pulled output files are
wiped on exit so every session starts clean.

---

## Keyboard Navigation

Evalflow is designed to be used entirely from the keyboard.

| Key | Action |
|-----|--------|
| `1` – `6` | Switch tabs |
| `?` | Open / close help panel |
| `q` | Quit |
| `Esc` | Unfocus current field |
| `↑` / `↓` | Move between fields on a page |
| `←` / `→` | Cycle between action buttons |
| `Enter` | Confirm / activate focused element |
| `Ctrl+R` | Check all watchers (Monitor tab) |
| `w` | Re-open setup wizard |

---

## Output Formats

After merging, Evalflow produces two CSVs ready for AI researchers to use directly.

### `evalflow_sft.csv` — SFT / fine-tuning format

One row per model response with score > 0, across all tasks and all models.

| Column | Description |
|--------|-------------|
| `task_name` | Benchmark task identifier |
| `task_description` | Human-readable task description |
| `model_name` | Full model identifier |
| `question` / `ground_truth` | Input and expected answer |
| `prompt_template` | Exact system prompt used |
| `messages` | Full conversation in `[{"role", "content"}]` JSON — SFT-ready |
| `llm_response` | Raw model output |
| `score` | Model score: `1.0`/`0.0` for boolean tasks, `0.0`–`1.0` for numeric tasks |
| `reasoning` | Failed assertion messages, pipe-separated |
| `assertions_json` | Full assertion array with statuses |
| `task_definition` | Source code of the task function |
| `judge_model` | Model used for response assessment (if any) |
| `input_tokens` / `output_tokens` | Token counts from the run |
| `timestamp` | ISO 8601 run timestamp |

### `evalflow_preferences.csv` — RLHF / DPO preference pairs

One row per question where models scored differently (highest-scoring vs lowest-scoring).
Column names match the HuggingFace TRL `DPOTrainer` convention.

| Column | Description |
|--------|-------------|
| `task_name` | Task identifier |
| `prompt` / `ground_truth` | Shared question and expected answer |
| `chosen` / `chosen_model` | Higher-scoring response and its model |
| `chosen_score` | Score of the chosen response |
| `rejected` / `rejected_model` | Lower-scoring response and its model |
| `rejected_score` | Score of the rejected response |
| `timestamp` | ISO 8601 timestamp |

Questions where all models score identically are excluded — they carry no preference signal.

---

## How Pull Works

The Pull tab takes a single **benchmark slug** (`username/benchmark-name`) and discovers all
task notebooks automatically using a 3-strategy fallback:

1. **Benchmark leaderboard API** — queries the Kaggle benchmark leaderboard to extract all
   task slugs that have been run. Most reliable when models have already been evaluated.
2. **Parent kernel lookup** — falls back to `kernels_list(parent=slug)` via the Kaggle SDK
   to find notebooks grouped under the benchmark.
3. **Single-task fallback** — if neither works, treats the slug itself as a single task.

The `outputs/` directory is wiped clean on every TUI launch so you always start fresh.

---

## Monitor — Automated Daily Updates

The Monitor tab (tab `6`) watches your benchmarks for new tasks and handles pull + merge +
publish automatically, with no manual steps.

**Adding a watcher:**
1. Enter the benchmark slug, dataset slug, dataset title, and whether to auto-publish
2. Click **Save Watcher**
3. Click a row in the table to load its settings back into the form for editing

**Running checks:**
- **Check All Now** — checks every watcher immediately
- **Check Selected** — checks only the highlighted watcher
- **Force Republish** — re-publishes the current merged outputs without waiting for new tasks
- **Reset & Re-pull** — clears known tasks for the selected watcher and re-pulls everything
- **View Dataset** — opens the published dataset on kaggle.com/datasets in your browser

**Daily schedule:**
- Set a time in `HH:MM` format and click **Save & Push**
- This commits the schedule to the GitHub Actions workflow file and pushes automatically
- The schedule runs on GitHub's servers — your machine can be off

**Syncing watchers to GitHub:**
Watcher configuration is stored as the `EVALFLOW_MANIFEST` GitHub Actions secret (not in the repo).
After every monitor run the secret is updated automatically — no manual syncing needed.
You can also force-sync from the Monitor tab using the **Sync Watchers → Secret** button.

**Headless / no machine required:**
The GitHub Actions workflow (`.github/workflows/evalflow_ci.yml`) runs `monitor.py --all`
on GitHub's servers every day at the time you configure, so your datasets update even
when your machine is off. See the CI section below.

---

## CI / GitHub Actions

`.github/workflows/evalflow_ci.yml` provides two modes:

### Daily schedule (automatic)

Runs every day at the time configured in the Monitor tab.
Calls `monitor.py --all`, which reads the `EVALFLOW_MANIFEST` GitHub Actions secret to
know which benchmarks to check and which dataset to publish to.

After each run the secret is automatically updated with any newly discovered tasks,
so the next scheduled run always has the latest state.

### Manual dispatch

Trigger via **Actions → Run workflow** with these inputs:

| Input | Example |
|-------|---------|
| `notebook_slug` | `your-username/your-benchmark-name` |
| `dataset_slug` | `your-benchmark-results` |
| `dataset_title` | `My Benchmark Results` |
| `update_existing` | `true` (after first publish) |

Required GitHub Secrets:

| Secret | Description |
|--------|-------------|
| `KAGGLE_USERNAME` | Your Kaggle username |
| `KAGGLE_KEY` | Your Kaggle legacy API key |
| `EVALFLOW_MANIFEST` | Watcher config JSON (auto-managed, create once with `{}`) |
| `GH_PAT` | Fine-grained GitHub PAT with Secrets read/write permission |

---

## Headless CLI

`monitor.py` can also be run directly without the TUI:

```bash
# Check all watchers defined in .evalflow_manifest.json
python monitor.py --all

# Check a single benchmark (reads its entry from the manifest)
python monitor.py username/benchmark-name
```

---

## Project Structure

```
evalflow/
├── evalflow.py              ← Textual app entry point + navigation
├── setup_wizard.py          ← First-run credential setup wizard
├── ci_runner.py             ← Headless pull/merge/publish for manual CI runs
├── monitor.py               ← Headless watcher runner (used by GitHub Actions)
├── config.py                ← .env-based configuration
├── requirements.txt
├── .evalflow_manifest.json  ← Watcher state (gitignored — synced via EVALFLOW_MANIFEST secret)
├── .github/
│   └── workflows/
│       └── evalflow_ci.yml  ← Daily schedule + manual dispatch CI
├── core/
│   ├── discovery.py         ← Shared benchmark task discovery via leaderboard API
│   ├── merger.py            ← Builds evalflow_sft.csv + evalflow_preferences.csv
│   └── uploader.py          ← Kaggle Datasets API wrapper (appends on update)
└── views/
    ├── pull_view.py         ← Auto-discovers + pulls all tasks
    ├── results_view.py      ← Browse outputs, filter by model / score
    ├── leaderboard_view.py  ← Cross-model ranking + per-question diff
    ├── merge_view.py        ← Merge into SFT + preference formats
    ├── publish_view.py      ← Upload both CSVs to Kaggle Datasets
    ├── monitor_view.py      ← Auto-watch benchmarks, manage schedule
    ├── help_view.py         ← In-app help panel
    └── widgets.py           ← Shared UI components
```

---

## License

MIT
