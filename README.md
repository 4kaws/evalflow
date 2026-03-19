```
███████╗██╗   ██╗ █████╗ ██╗     ███████╗██╗      ██████╗ ██╗    ██╗
██╔════╝██║   ██║██╔══██╗██║     ██╔════╝██║     ██╔═══██╗██║    ██║
█████╗  ╚██╗ ██╔╝███████║██║     █████╗  ██║     ██║   ██║██║ █╗ ██║
██╔══╝   ╚████╔╝ ██╔══██║██║     ██╔══╝  ██║     ██║   ██║██║███╗██║
███████╗  ╚██╔╝  ██║  ██║███████╗██║     ███████╗╚██████╔╝╚███╔███╔╝
╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝
```

A terminal UI for pulling Kaggle Community Benchmark results, merging them into
publication-ready datasets, and publishing them to Kaggle Datasets — all from the terminal.

You write your benchmark on Kaggle. Kaggle runs it against as many models as you want
for free. Evalflow handles everything after that: one slug, all tasks pulled at once,
two research-ready CSVs produced, published to Kaggle Datasets in one click.

---

## Workflow

```
Kaggle (browser)                              Evalflow (terminal)
─────────────────────────────────────         ──────────────────────────────────────
1. Write your task notebooks                  5. Pull
   (use notebooks/notebook_template.ipynb)       Paste your benchmark slug once.
   One notebook per task.                        Evalflow auto-discovers all task
                                                 notebooks and downloads every CSV.
2. Group them into a Benchmark
   on kaggle.com/benchmarks                   6. Results
                                                 Browse pulled CSVs, filter by
3. Click Add Models on the                       model and pass/fail score.
   Benchmark page to run across
   Claude, Gemini, Llama, DeepSeek          7. Leaderboard
   (free, within quota)                         Cross-model accuracy ranking with
                                                 per-question pass/fail diff.
4. Kaggle produces one output CSV
   per task per model                        8. Merge
                                                 Combines all CSVs into two files:
                                                   evalflow_sft.csv
                                                   evalflow_preferences.csv

                                             9. Publish
                                                 Uploads both to Kaggle Datasets
                                                 as a free public resource.
```

---

## Installation

### Linux

```bash
# Python 3.12+ is required
python3 --version

git clone https://github.com/your-username/evalflow.git
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

git clone https://github.com/your-username/evalflow.git
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
git clone https://github.com/your-username/evalflow.git
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

The setup wizard launches automatically on first run and asks for your Kaggle credentials.
You can also skip it and create a `.env` file manually:

```env
KAGGLE_USERNAME=your-username
KAGGLE_KEY=your-legacy-api-key
```

Get your key at: **kaggle.com → Settings → Account → Legacy API Credentials → Create Legacy API Key**

Credentials are saved to `.env` and persist between sessions. All pulled CSV files are
wiped on exit so every session starts clean.

---

## Keyboard Navigation

Evalflow is designed to be used entirely from the keyboard.

| Key | Action |
|-----|--------|
| `1` – `5` | Switch tabs |
| `?` | Open / close help panel |
| `q` | Quit |
| `Esc` | Unfocus current field |
| `↑` / `↓` | Move between fields on a page |
| `←` / `→` | Cycle between action buttons |
| `Enter` | Confirm / activate focused element |

**On Pull tab:** navigate from the slug field down through all fields to the button row, then cycle through Pull All Tasks / List tasks only / Open on Kaggle with `←` / `→`.

**On Merge tab:** navigate to the button row, then cycle through Merge Selected / Refresh / Select All.

**On Publish tab:** navigate from Kaggle username down through all fields; after choosing a license the cursor jumps automatically to the button row where you cycle Publish New / Update Existing.

---

## Output Formats

After merging, Evalflow produces two CSVs ready for AI researchers to use directly.

### `evalflow_sft.csv` — SFT / fine-tuning format

One row per model response, across all tasks and all models.

| Column | Description |
|--------|-------------|
| `task_name` | Benchmark task identifier |
| `category` / `difficulty` | For slice analysis and curriculum filtering |
| `model_name` / `model_version` | Full model identifier |
| `question` / `ground_truth` | Input and expected answer |
| `prompt_template` | Exact system prompt used |
| `messages` | Full conversation in `[{"role", "content"}]` JSON — SFT-ready |
| `llm_response` | Raw model output |
| `answer_correct` | Did the model get the right answer? (0/1) |
| `reasoning_correct` | Was the reasoning valid? (0/1) |
| `score` | Overall pass/fail (0/1) |
| `reasoning` | Judge explanation when score = 0 |
| `judge_model` | Model used to judge the response |
| `timestamp` | ISO 8601 run timestamp |

### `evalflow_preferences.csv` — RLHF / DPO preference pairs

One row per question where at least one model **passed** and at least one **failed**.
Built automatically at merge time — no extra work needed.

| Column | Description |
|--------|-------------|
| `task_name` / `category` / `difficulty` | Task metadata |
| `question` / `ground_truth` / `prompt_template` | Shared question metadata |
| `chosen_response` / `chosen_model` | Best passing response |
| `rejected_response` / `rejected_model` | Worst failing response |

Questions where all models pass or all fail are excluded — they carry no preference signal.

---

## How Pull Works

The Pull tab takes a single **benchmark slug** and discovers all task notebooks automatically:

1. **REST API search** — searches Kaggle's kernel API for all notebooks matching your prefix. Works reliably regardless of SDK version.
2. **SDK fallback** — falls back to the Kaggle Python SDK if the REST call fails.
3. **Single-task fallback** — if neither works, treats the slug itself as a single task.

Each task CSV is prefixed with the task's short name before saving, so outputs from multiple tasks and models land in `outputs/` without collisions. The `outputs/` directory is wiped clean on every launch so you always start fresh.

---

## Your Benchmark Notebook

`notebooks/notebook_template.ipynb` is the starting point for writing benchmark tasks. The only things to customise:

1. `TASK_NAME` — your task identifier
2. `PROMPT_TEMPLATE` — your system prompt
3. `EVALUATION_DATA` — your questions and answers
4. `CRITERIA` — what the judge checks (criterion 0 → `answer_correct`, criterion 1 → `reasoning_correct`)
5. `%choose your-task-name` in the last cell — submits to the Kaggle leaderboard

Upload to Kaggle, hit **Save Version**, group it into a Benchmark, then use **Add Models**
to run it across multiple LLMs — free within your Kaggle quota.

---

## CI / GitHub Actions

`.github/workflows/evalflow_ci.yml` runs the full pipeline headlessly without opening the TUI.

Trigger via **Actions → Run workflow**:

| Input | Example |
|-------|---------|
| `notebook_slug` | `your-username/your-benchmark-name` |
| `dataset_slug` | `your-benchmark-results` |
| `dataset_title` | `My Benchmark Results` |
| `update_existing` | `true` (after first publish) |

Required GitHub Secrets:
```
KAGGLE_USERNAME
KAGGLE_KEY
```

---

## Project Structure

```
evalflow/
├── evalflow.py              ← Textual app entry point + navigation
├── setup_wizard.py          ← First-run credential setup wizard
├── ci_runner.py             ← Headless pull/merge/publish for CI
├── config.py                ← .env-based configuration
├── requirements.txt
├── .github/
│   └── workflows/
│       └── evalflow_ci.yml  ← CI: pull → merge → publish
├── core/
│   ├── merger.py            ← Builds evalflow_sft.csv + evalflow_preferences.csv
│   └── uploader.py          ← Kaggle Datasets API wrapper
├── views/
│   ├── pull_view.py         ← Auto-discovers + pulls all tasks
│   ├── results_view.py      ← Browse CSVs, filter by model / score
│   ├── leaderboard_view.py  ← Cross-model ranking + per-question diff
│   ├── merge_view.py        ← Merge into SFT + preference formats
│   ├── publish_view.py      ← Upload both CSVs to Kaggle Datasets
│   └── help_view.py         ← In-app help panel
└── notebooks/
    └── notebook_template.ipynb  ← Template for benchmark task authors
```

---

## License

MIT
