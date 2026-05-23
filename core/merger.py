"""
Merge multiple benchmark .run.json files into two publication-ready formats:

  Format A — SFT-ready  (evalflow_sft.csv / .parquet)
      One row per passing model response. Includes the full conversation,
      per-assertion reasoning, token metrics, timestamps, ground truth,
      and task definition.

  Format B — Preference pairs  (evalflow_preferences.csv / .parquet)
      Sampled all-pairs: up to max_pairs_per_question (passing × failing)
      combinations per question. Column names match HuggingFace TRL
      DPOTrainer convention (prompt / chosen / rejected).
"""

import json
import random
import re
import zlib
from datetime import datetime
from pathlib import Path

import pandas as pd


# ── Column definitions ──────────────────────────────────────────────────────

SFT_COLUMNS = [
    "task_name",
    "task_description",
    "model_name",
    "question",
    "ground_truth",
    "prompt_template",
    "llm_response",
    "messages",
    "score",
    "reasoning",
    "assertions_json",
    "task_definition",
    "judge_model",
    "input_tokens",
    "output_tokens",
    "timestamp",
]

PREF_COLUMNS = [
    "task_name",
    "prompt",          # renamed from "question" — matches TRL DPOTrainer convention
    "ground_truth",
    "chosen",          # renamed from "chosen_response"
    "chosen_model",
    "rejected",        # renamed from "rejected_response"
    "rejected_model",
    "timestamp",
]


# ── Public API ──────────────────────────────────────────────────────────────

def discover_outputs(output_dir: Path) -> list[Path]:
    """Return benchmark .run.json files sorted by modification time."""
    if not output_dir.exists():
        return []
    return sorted(
        output_dir.glob("*.run.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def validate_run_json(path: Path) -> tuple[bool, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "taskVersion" not in data:
            return False, "Missing taskVersion"
        if "modelVersion" not in data:
            return False, "Missing modelVersion"
        if not data.get("conversations"):
            return False, "No conversations"
        return True, "OK"
    except Exception as exc:
        return False, str(exc)


def parse_run_json(path: Path) -> tuple[dict | None, str]:
    """
    Parse a single .run.json into a flat row dict.
    Returns (row_dict, "") on success, or (None, reason) on failure.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"JSON parse error: {exc}"

    task_ver   = data.get("taskVersion", {})
    task_name  = task_ver.get("name", "")
    model_slug = data.get("modelVersion", {}).get("slug", "")
    end_time   = data.get("endTime", datetime.now().isoformat())

    # ── Find main task conversation (not the judge assessment) ────────────
    conversations = data.get("conversations", [])
    main_conv = next(
        (c for c in conversations if "Response assessment" not in c.get("id", "")),
        conversations[0] if conversations else None,
    )
    if not main_conv:
        return None, "No conversations found"

    # Walk all requests — handles multi-turn tasks correctly
    question     = ""
    llm_response = ""
    prompt_template = ""
    raw_messages = []

    for req in main_conv.get("requests", []):
        for content in req.get("contents", []):
            role  = content.get("role", "")
            parts = content.get("parts", [])
            text  = parts[0].get("text", "") if parts else ""
            if role == "CONTENT_ROLE_SYSTEM" and not prompt_template:
                prompt_template = text
            elif role == "CONTENT_ROLE_USER" and not question:
                question = text
                raw_messages.append({"role": "user", "content": text})
            elif role == "CONTENT_ROLE_ASSISTANT" and not llm_response:
                llm_response = text
                raw_messages.append({"role": "assistant", "content": text})

    if not prompt_template:
        prompt_template = question  # bare prompt — the question is the full template

    if not question:
        return None, "Could not extract question (no CONTENT_ROLE_USER turn)"
    if not llm_response:
        return None, "Could not extract LLM response (no CONTENT_ROLE_ASSISTANT turn)"

    # ── Overall pass/fail ─────────────────────────────────────────────────
    score = 0
    for r in data.get("results", []):
        if r.get("type") == "AGGREGATED":
            score = int(r.get("booleanResult", False))
            break

    # ── Ground truth from assertion definitions ───────────────────────────
    # Handles assert_in("expected", response), assert_equals, assert_contains
    _ASSERT_RE = re.compile(
        r'assert_(?:in|equals|contains)\(\s*["\']([^"\']+)["\']', re.IGNORECASE
    )
    ground_truth = ""
    for a in data.get("assertions", []):
        m = _ASSERT_RE.search(a.get("definition", ""))
        if m:
            ground_truth = m.group(1)
            break

    # ── Reasoning from failed assertions ──────────────────────────────────
    failed = [
        a.get("expectation", "")
        for a in data.get("assertions", [])
        if a.get("status") != "BENCHMARK_TASK_RUN_ASSERTION_STATUS_PASSED"
    ]
    reasoning = " | ".join(failed) if failed else ""

    # ── Full assertions array (all statuses) ──────────────────────────────
    assertions_json = json.dumps(data.get("assertions", []), ensure_ascii=False)

    # ── Judge model ───────────────────────────────────────────────────────
    judge_conv = next(
        (c for c in conversations if "Response assessment" in c.get("id", "")),
        None,
    )
    judge_model = ""
    if judge_conv:
        for content in judge_conv.get("requests", [{}])[0].get("contents", []):
            if content.get("role") == "CONTENT_ROLE_ASSISTANT":
                judge_model = content.get("senderName", "")

    # ── Token metrics ─────────────────────────────────────────────────────
    metrics = main_conv.get("metrics", {})

    return {
        "task_name":        task_name,
        "task_description": task_ver.get("description", ""),
        "task_definition":  task_ver.get("definition", ""),
        "model_name":       model_slug,
        "question":         question,
        "ground_truth":     ground_truth,
        "prompt_template":  prompt_template,
        "llm_response":     llm_response,
        "messages":         json.dumps(raw_messages, ensure_ascii=False),
        "score":            score,
        "reasoning":        reasoning,
        "assertions_json":  assertions_json,
        "judge_model":      judge_model,
        "input_tokens":     metrics.get("inputTokens", 0),
        "output_tokens":    metrics.get("outputTokens", 0),
        "timestamp":        end_time,
    }, ""


def merge_outputs(
    json_paths: list[Path],
    output_dir: Path,
    deduplicate: bool = True,
    passing_only: bool = True,
    max_pairs_per_question: int = 8,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Parse .run.json files and merge into Format A (SFT) and Format B (preferences).

    passing_only: when True (default), SFT file contains only score==1 rows —
    correct demonstrations for fine-tuning. Preferences always use all rows.

    max_pairs_per_question: cap on preference pairs per question to prevent
    questions with many model runs from dominating the training signal.
    Excess pairs are sampled deterministically (seeded on task+question).

    Returns (sft_df, pref_df, stats).
    Writes evalflow_sft.csv/.parquet and evalflow_preferences.csv/.parquet to output_dir.
    """
    if not json_paths:
        raise ValueError("No .run.json paths provided")

    rows, skipped = [], []
    for path in json_paths:
        row, reason = parse_run_json(path)
        if row is None:
            skipped.append((path.name, reason))
        else:
            rows.append(row)

    if not rows:
        raise ValueError(f"No valid run files. Skipped: {skipped}")

    raw = pd.DataFrame(rows)

    if deduplicate:
        before = len(raw)
        raw = raw.drop_duplicates(
            subset=["task_name", "model_name", "question", "llm_response"]
        )
        dupes_removed = before - len(raw)
    else:
        dupes_removed = 0

    sft_raw = raw[raw["score"] == 1].reset_index(drop=True) if passing_only else raw
    sft_df  = _build_sft(sft_raw)
    pref_df = _build_preferences(raw, max_pairs_per_question=max_pairs_per_question)

    output_dir.mkdir(parents=True, exist_ok=True)
    sft_path  = output_dir / "evalflow_sft.csv"
    pref_path = output_dir / "evalflow_preferences.csv"
    sft_df.to_csv(sft_path,  index=False)
    pref_df.to_csv(pref_path, index=False)

    parquet_written = _write_parquet(sft_df, pref_df, output_dir)

    pref_questions = pref_df["prompt"].nunique() if not pref_df.empty else 0

    stats = {
        "total_rows":             len(sft_df),
        "files_merged":           len(rows),
        "files_skipped":          len(skipped),
        "duplicates_removed":     dupes_removed,
        "models":                 raw["model_name"].nunique(),
        "tasks":                  raw["task_name"].nunique(),
        "accuracy":               round(raw["score"].mean() * 100, 1),
        "preference_pairs":       len(pref_df),
        "pref_questions":         pref_questions,
        "max_pairs_per_question": max_pairs_per_question,
        "sft_path":               str(sft_path),
        "pref_path":              str(pref_path),
        "parquet_written":        parquet_written,
        "skipped_details":        skipped,
        "passing_only":           passing_only,
    }

    return sft_df, pref_df, stats


# ── Format A — SFT ──────────────────────────────────────────────────────────

def _build_sft(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    extra   = [c for c in df.columns if c not in SFT_COLUMNS]
    ordered = [c for c in SFT_COLUMNS if c in df.columns] + extra
    return df[ordered]


# ── Format B — Preference pairs ─────────────────────────────────────────────

def _build_preferences(raw: pd.DataFrame, max_pairs_per_question: int = 8) -> pd.DataFrame:
    """
    All-pairs up to max_pairs_per_question per question.

    Column names match HuggingFace TRL DPOTrainer: prompt / chosen / rejected.
    When the full product exceeds the cap, pairs are shuffled with a seed
    derived from task+question so the same inputs always yield the same sample.
    """
    pairs = []
    for (task_name, question), grp in raw.groupby(["task_name", "question"]):
        passed = grp[grp["score"] == 1]
        failed = grp[grp["score"] == 0]
        if passed.empty or failed.empty:
            continue

        ground_truth = grp["ground_truth"].iloc[0] if "ground_truth" in grp.columns else ""
        ts = datetime.now().isoformat()

        question_pairs = [
            {
                "task_name":     task_name,
                "prompt":        question,
                "ground_truth":  ground_truth,
                "chosen":        chosen_row["llm_response"],
                "chosen_model":  chosen_row["model_name"],
                "rejected":      rejected_row["llm_response"],
                "rejected_model": rejected_row["model_name"],
                "timestamp":     ts,
            }
            for _, chosen_row in passed.iterrows()
            for _, rejected_row in failed.iterrows()
        ]

        if len(question_pairs) > max_pairs_per_question:
            # zlib.crc32 is stable across Python sessions (unlike hash(), which is PYTHONHASHSEED-salted)
            seed = zlib.crc32(f"{task_name}:{question}".encode())
            random.Random(seed).shuffle(question_pairs)
            question_pairs = question_pairs[:max_pairs_per_question]

        pairs.extend(question_pairs)

    if not pairs:
        return pd.DataFrame(columns=PREF_COLUMNS)
    df = pd.DataFrame(pairs)
    return df[[c for c in PREF_COLUMNS if c in df.columns]]


# ── Parquet output (optional — requires pyarrow) ─────────────────────────────

def _write_parquet(sft_df: pd.DataFrame, pref_df: pd.DataFrame, output_dir: Path) -> bool:
    """Write .parquet alongside .csv; returns True if successful."""
    try:
        import pyarrow  # noqa: F401
        sft_df.to_parquet(output_dir / "evalflow_sft.parquet",          index=False)
        pref_df.to_parquet(output_dir / "evalflow_preferences.parquet", index=False)
        return True
    except ImportError:
        return False
