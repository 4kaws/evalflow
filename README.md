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
   (use notebooks/notebook_template.ipynb)       Paste your benchmark slug once.
   One notebook per task.                        Evalflow auto-discovers all task
                                                 notebooks and downloads every
2. Group them into a Benchmark                   .run.json output file.
   on kaggle.com/benchmarks
                                             6. Results
3. Click Add Models on the                       Browse pulled data, filter by
   Benchmark page to run across                  model and pass/fail score.
   Claude, Gemini, Llama, DeepSeek
   (free, within quota)                      7. Leaderboard
                                                 Cross-model accuracy ranking with
4. Kaggle runs each task notebook                per-question pass/fail diff.
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

The setup wizard launches automatically on first run and asks for your Kaggle credentials.
You can also skip it and create a `.env` file manually:

```env
KAGGLE_USERNAME=your-username
KAGGLE_KEY=your-legacy-api-key
```

Get your key at: **kaggle.com → Settings → Account → Legacy API Credentials → Create Legacy API Key**

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
| `score` | Overall pass/fail (0/1) |
| `input_tokens` / `output_tokens` | Token counts from the run |
| `timestamp` | ISO 8601 run timestamp |

### `evalflow_preferences.csv` — RLHF / DPO preference pairs

One row per question where at least one model **passed** and at least one **failed**.
Built automatically at merge time — no extra work needed.

| Column | Description |
|--------|-------------|
| `task_name` | Task identifier |
| `question` / `ground_truth` | Shared question metadata |
| `chosen_response` / `chosen_model` | Best passing response |
| `rejected_response` / `rejected_model` | Worst failing response |
| `timestamp` | ISO 8601 timestamp |

Questions where all models pass or all fail are excluded — they carry no preference signal.

---

## How Pull Works

The Pull tab takes a single **benchmark slug** (`username/benchmark-name`) and discovers all
task notebooks automatically using a 3-strategy fallback:

1. **Benchmark leaderboard API** — queries the Kaggle benchmark leaderboard to extract all
   task slugs that have been run. Most reliable when models have already been evaluated.
2. **Parent kernel lookup** — falls back to `kernels_list(parent=slug)` via the Kaggle SDK
   to find notebooks grouped under the benchmark.
3. **Single-task fallback** — if neither works, treats the slug itself as a single task.

Output files are prefixed with the task's short name before saving, so files from multiple
tasks land in `outputs/` without collisions. The `outputs/` directory is wiped clean on
every TUI launch so you always start fresh.

---

## Monitor — Automated Daily Updates

The Monitor tab (tab `6`) watches your benchmarks for new tasks and handles pull + merge +
publish automatically, with no manual steps.

**Adding a watcher:**
1. Enter the benchmark slug, dataset slug, dataset title, and whether to auto-publish
2. Click **Add / Update Watcher**
3. Click a row in the table to load its settings back into the form for editing

**Running checks:**
- **Check All Now** — checks every watcher immediately
- **Check Selected** — checks only the highlighted watcher
- **Force Republish Selected** — re-publishes the current merged outputs without waiting for new tasks

**Daily schedule:**
- Set a time in `HH:MM` format, enable the checkbox, and click **Save Schedule**
- This writes a crontab entry that runs `monitor.py --all` at the given time every day
- The schedule runs independently of the TUI — you do not need the app open

**Syncing watchers with GitHub Actions:**
The Monitor tab has a **Push to GitHub** button. After adding or updating a watcher,
click it to commit and push `.evalflow_manifest.json` directly from the TUI — no
terminal needed. GitHub Actions reads this file on every scheduled run, so pushing
keeps the cloud schedule in sync with your local watcher configuration.

You can also do this manually:
```bash
git add .evalflow_manifest.json
git commit -m "update: monitor manifest"
git push
```

**Headless / no machine required:**
The GitHub Actions workflow (`.github/workflows/evalflow_ci.yml`) runs the same
`monitor.py --all` on GitHub's servers every day at 08:00 Bucharest time (06:00 UTC),
so your datasets update even when your machine is off. See the CI section below.

Both the local cron and GitHub Actions can run simultaneously — the dataset
append + deduplication logic prevents any duplicate data.

---

## Your Benchmark Notebook

`notebooks/notebook_template.ipynb` is the starting point for writing benchmark tasks.
It uses the `kbench` library format:

**Cell 1** — lists all available models:
```python
import kbench
for m in kbench.available_models():
    print(m)
```

**Cell 2** — defines your task and runs it against each model:
```python
MODELS = [
    "google/gemini-2.5-flash",
    "anthropic/claude-opus-4-6@default",
    # add or remove models here
]

@kbench.task(name="What is Kaggle?", description="Does the LLM know what Kaggle is?")
def what_is_kaggle(llm) -> None:
    response = llm.prompt("What is Kaggle?")
    kbench.assertions.assert_in("data science", response.lower())

for model in MODELS:
    what_is_kaggle.run(model)
```

Customise `name`, `description`, the prompt, the assertion logic, and the `MODELS` list.
Upload to Kaggle, hit **Save Version**, group it into a Benchmark, then use **Add Models**
to run it across multiple LLMs — free within your Kaggle quota.

---

## CI / GitHub Actions

`.github/workflows/evalflow_ci.yml` provides two modes:

### Daily schedule (automatic)

Runs every day at **08:00 EET / 09:00 EEST (06:00 UTC)** on GitHub's servers.
Calls `monitor.py --all`, which reads `.evalflow_manifest.json` from the repo to know
which benchmarks to check and which dataset to publish to.

To keep the schedule in sync with your watchers, commit `.evalflow_manifest.json`
after adding or updating watchers in the Monitor tab:
```bash
git add .evalflow_manifest.json
git commit -m "update monitor manifest"
git push
```

### Manual dispatch

Trigger via **Actions → Run workflow** with these inputs:

| Input | Example |
|-------|---------|
| `notebook_slug` | `your-username/your-benchmark-name` |
| `dataset_slug` | `your-benchmark-results` |
| `dataset_title` | `My Benchmark Results` |
| `update_existing` | `true` (after first publish) |

Required GitHub Secrets for both modes:
```
KAGGLE_USERNAME
KAGGLE_KEY
```

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
├── monitor.py               ← Headless watcher runner (used by cron + GitHub Actions)
├── config.py                ← .env-based configuration
├── requirements.txt
├── .evalflow_manifest.json  ← Watcher state (committed so GitHub Actions can read it)
├── .github/
│   └── workflows/
│       └── evalflow_ci.yml  ← Daily schedule + manual dispatch CI
├── core/
│   ├── merger.py            ← Builds evalflow_sft.csv + evalflow_preferences.csv
│   └── uploader.py          ← Kaggle Datasets API wrapper (appends on update)
├── views/
│   ├── pull_view.py         ← Auto-discovers + pulls all tasks
│   ├── results_view.py      ← Browse outputs, filter by model / score
│   ├── leaderboard_view.py  ← Cross-model ranking + per-question diff
│   ├── merge_view.py        ← Merge into SFT + preference formats
│   ├── publish_view.py      ← Upload both CSVs to Kaggle Datasets
│   ├── monitor_view.py      ← Auto-watch benchmarks, manage schedule
│   └── help_view.py         ← In-app help panel
└── notebooks/
    └── notebook_template.ipynb  ← Template for benchmark task authors
```

---

## License

MIT
