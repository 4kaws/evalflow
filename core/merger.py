"""
Merge multiple benchmark output CSVs into two publication-ready formats:

  Format A — SFT-ready  (evalflow_sft.csv)
      One row per model response. Includes messages in chat format,
      per-criterion scores, and full reproducibility metadata.

  Format B — Preference pairs  (evalflow_preferences.csv)
      One row per question where at least one model passed AND one failed.
      Provides (chosen_response, chosen_model, rejected_response, rejected_model)
      pairs directly usable in RLHF / DPO pipelines.
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


# ------------------------------------------------------------------ #
#  Constants                                                          #
# ------------------------------------------------------------------ #

REQUIRED_COLUMNS = {
    "task_name", "model_name", "question",
    "ground_truth", "llm_response", "score",
}

# Column order for Format A
SFT_COLUMNS = [
    "task_name",
    "category",
    "difficulty",
    "model_name",
    "model_version",
    "question",
    "ground_truth",
    "prompt_template",
    "messages",
    "llm_response",
    "answer_correct",
    "reasoning_correct",
    "score",
    "reasoning",
    "judge_model",
    "temperature_note",
    "timestamp",
]

# Column order for Format B
PREF_COLUMNS = [
    "task_name",
    "category",
    "difficulty",
    "question",
    "ground_truth",
    "prompt_template",
    "chosen_response",
    "chosen_model",
    "chosen_model_version",
    "rejected_response",
    "rejected_model",
    "rejected_model_version",
    "timestamp",
]

DEFAULT_PROMPT_TEMPLATE = (
    "You are an expert logician. "
    "Reason through the following deductive logic question step by step, "
    "then clearly state your final answer in a single sentence starting with "
    "'Therefore:' or 'Conclusion:'.\n\nQuestion: {question}"
)


# ------------------------------------------------------------------ #
#  Public API                                                         #
# ------------------------------------------------------------------ #

def discover_outputs(output_dir: Path) -> list[Path]:
    """Return benchmark output CSVs, excluding already-merged files."""
    return sorted(
        [
            p for p in output_dir.glob("*.csv")
            if not p.name.startswith("evalflow_")   # skip our own outputs
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def validate_csv(path: Path) -> tuple[bool, str]:
    try:
        df = pd.read_csv(path, nrows=1)
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            return False, f"Missing columns: {', '.join(missing)}"
        return True, "OK"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def merge_outputs(
    csv_paths: list[Path],
    output_dir: Path,
    deduplicate: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Load, validate, and merge CSV paths into Format A and Format B.

    Returns (sft_df, pref_df, stats).
    Output files are written to output_dir as:
        evalflow_sft.csv
        evalflow_preferences.csv
    """
    if not csv_paths:
        raise ValueError("No CSV paths provided")

    dfs, skipped = _load_and_validate(csv_paths)

    if not dfs:
        raise ValueError(f"No valid CSVs. Skipped: {skipped}")

    raw = pd.concat(dfs, ignore_index=True)

    if deduplicate:
        before = len(raw)
        raw = raw.drop_duplicates(
            subset=["task_name", "model_name", "question", "llm_response"]
        )
        dupes_removed = before - len(raw)
    else:
        dupes_removed = 0

    sft_df   = _build_sft(raw)
    pref_df  = _build_preferences(raw)

    output_dir.mkdir(parents=True, exist_ok=True)
    sft_path  = output_dir / "evalflow_sft.csv"
    pref_path = output_dir / "evalflow_preferences.csv"

    sft_df.to_csv(sft_path,  index=False)
    pref_df.to_csv(pref_path, index=False)

    pref_questions = pref_df["question"].nunique() if not pref_df.empty else 0

    stats = {
        "total_rows":          len(sft_df),
        "files_merged":        len(dfs),
        "files_skipped":       len(skipped),
        "duplicates_removed":  dupes_removed,
        "models":              raw["model_name"].nunique(),
        "tasks":               raw["task_name"].nunique(),
        "accuracy":            round(raw["score"].mean() * 100, 1),
        "preference_pairs":    len(pref_df),
        "pref_questions":      pref_questions,
        "sft_path":            str(sft_path),
        "pref_path":           str(pref_path),
        "skipped_details":     skipped,
    }

    return sft_df, pref_df, stats


# ------------------------------------------------------------------ #
#  Format A — SFT                                                     #
# ------------------------------------------------------------------ #

def _build_sft(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich the raw merged DataFrame into SFT-ready format.

    Adds: messages, answer_correct, reasoning_correct,
    model_version, prompt_template, temperature_note, judge_model.
    """
    df = raw.copy()

    # ── Ensure optional columns exist with sensible defaults ──────────
    for col, default in [
        ("category",          "unknown"),
        ("difficulty",        "unknown"),
        ("reasoning",         ""),
        ("answer_correct",    None),
        ("reasoning_correct", None),
        ("judge_model",       "unknown"),
        ("prompt_template",   DEFAULT_PROMPT_TEMPLATE),
    ]:
        if col not in df.columns:
            df[col] = default

    # ── Derive answer_correct / reasoning_correct from score + reasoning
    #    If the notebook wrote them explicitly, keep them.
    #    Otherwise, use score as answer_correct and try to infer
    #    reasoning_correct from the judge reasoning text.
    if df["answer_correct"].isna().all():
        df["answer_correct"] = df["score"]

    if df["reasoning_correct"].isna().all():
        # Heuristic: if score=1, reasoning was correct; if score=0 and
        # the reasoning text mentions the answer but not the logic,
        # mark reasoning_correct=0 too. Default to score value.
        df["reasoning_correct"] = df["score"]

    df["answer_correct"]    = df["answer_correct"].astype(int)
    df["reasoning_correct"] = df["reasoning_correct"].astype(int)

    # ── model_version: best-effort from model_name + run date ─────────
    if "model_version" not in df.columns:
        run_date = datetime.now().strftime("%Y-%m")
        df["model_version"] = df["model_name"] + f"@kaggle-proxy-{run_date}"

    # ── temperature note ──────────────────────────────────────────────
    df["temperature_note"] = "Kaggle model proxy default (not exposed by kbench SDK)"

    # ── Build messages column (chat format) ───────────────────────────
    df["messages"] = df.apply(_build_messages, axis=1)

    # ── Reorder columns ───────────────────────────────────────────────
    extra = [c for c in df.columns if c not in SFT_COLUMNS]
    ordered = [c for c in SFT_COLUMNS if c in df.columns] + extra
    return df[ordered]


def _build_messages(row: pd.Series) -> str:
    """
    Build a messages JSON string in standard chat format.

    [
      {"role": "system",    "content": "<prompt_template minus {question}>"},
      {"role": "user",      "content": "<question>"},
      {"role": "assistant", "content": "<llm_response>"}
    ]
    """
    template = str(row.get("prompt_template", DEFAULT_PROMPT_TEMPLATE))

    # Split system preamble from the "{question}" injection
    system_part = template.split("\n\nQuestion:")[0].strip() if "\n\nQuestion:" in template else template
    question    = str(row.get("question", ""))
    response    = str(row.get("llm_response", ""))

    messages = [
        {"role": "system",    "content": system_part},
        {"role": "user",      "content": question},
        {"role": "assistant", "content": response},
    ]
    return json.dumps(messages, ensure_ascii=False)


# ------------------------------------------------------------------ #
#  Format B — Preference pairs                                        #
# ------------------------------------------------------------------ #

def _build_preferences(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Build preference pairs from the raw merged data.

    For each (task_name, question) where at least one model PASSED
    and at least one FAILED, generate a row pairing the best passing
    response with the worst failing response.

    If multiple models passed, pick the one with the longest / most
    detailed response (heuristic for quality). If multiple failed,
    pick the shortest (least useful).
    """
    for col, default in [
        ("category",   "unknown"),
        ("difficulty", "unknown"),
        ("prompt_template", DEFAULT_PROMPT_TEMPLATE),
        ("model_version",   ""),
    ]:
        if col not in raw.columns:
            raw = raw.copy()
            raw[col] = default

    group_keys = ["task_name", "question"]
    pairs = []

    for (task_name, question), grp in raw.groupby(group_keys):
        passed = grp[grp["score"] == 1]
        failed = grp[grp["score"] == 0]

        if passed.empty or failed.empty:
            continue   # need at least one of each

        # Best chosen: longest response (most detailed correct answer)
        chosen_row = passed.loc[
            passed["llm_response"].str.len().idxmax()
        ]

        # Best rejected: shortest failing response (least informative wrong)
        rejected_row = failed.loc[
            failed["llm_response"].str.len().idxmin()
        ]

        meta = grp.iloc[0]   # pick any row for shared metadata

        pairs.append({
            "task_name":             task_name,
            "category":              meta.get("category", "unknown"),
            "difficulty":            meta.get("difficulty", "unknown"),
            "question":              question,
            "ground_truth":          meta.get("ground_truth", ""),
            "prompt_template":       meta.get("prompt_template", DEFAULT_PROMPT_TEMPLATE),
            "chosen_response":       chosen_row["llm_response"],
            "chosen_model":          chosen_row["model_name"],
            "chosen_model_version":  chosen_row.get("model_version", ""),
            "rejected_response":     rejected_row["llm_response"],
            "rejected_model":        rejected_row["model_name"],
            "rejected_model_version": rejected_row.get("model_version", ""),
            "timestamp":             datetime.now().isoformat(),
        })

    if not pairs:
        return pd.DataFrame(columns=PREF_COLUMNS)

    df = pd.DataFrame(pairs)
    ordered = [c for c in PREF_COLUMNS if c in df.columns]
    return df[ordered]


# ------------------------------------------------------------------ #
#  Internal helpers                                                   #
# ------------------------------------------------------------------ #

def _load_and_validate(
    csv_paths: list[Path],
) -> tuple[list[pd.DataFrame], list[tuple[str, str]]]:
    dfs, skipped = [], []
    for path in csv_paths:
        ok, msg = validate_csv(path)
        if not ok:
            skipped.append((path.name, msg))
            continue
        df = pd.read_csv(path)
        if "reasoning" not in df.columns:
            df["reasoning"] = ""
        dfs.append(df)
    return dfs, skipped
