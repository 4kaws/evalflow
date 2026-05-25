"""
Merge multiple benchmark .run.json files into two publication-ready formats:

  Format A — SFT-ready  (evalflow_sft.csv / .parquet)
      One row per model response per subtask. For single-request tasks this
      is one row per file; for multi-subtask tasks it is one row per subtask,
      each a coherent (question, answer) pair. Includes the full conversation,
      per-assertion reasoning, token metrics, timestamps, ground truth,
      and task definition.

  Format B — Preference pairs  (evalflow_preferences.csv / .parquet)
      All model pairs for each (task, question) where scores differ by >= 0.2.
      Column names match HuggingFace TRL DPOTrainer convention
      (prompt / chosen / rejected).
"""

from __future__ import annotations

import itertools
import json
import random
import re
import zlib
from datetime import datetime
from pathlib import Path

import pandas as pd


SFT_FILENAME  = "evalflow_sft.csv"
PREF_FILENAME = "evalflow_preferences.csv"


def row_count(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            return str(sum(1 for _ in f) - 1)
    except Exception:
        return "?"


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
    "chosen_score",
    "rejected",        # renamed from "rejected_response"
    "rejected_model",
    "rejected_score",
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


def parse_run_json(path: Path) -> tuple[list[dict], str]:
    """
    Parse a .run.json into one row per request (one prompt → one response).

    Multi-subtask tasks produce N rows — one per subtask — each a coherent
    single-turn Q&A. Single-request tasks produce one row as before.
    All rows from the same file share the same aggregate score.

    Returns (rows, "") on success, or ([], reason) on failure.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], f"JSON parse error: {exc}"

    task_ver   = data.get("taskVersion", {})
    task_name  = task_ver.get("name", "")
    model_slug = data.get("modelVersion", {}).get("slug", "")
    end_time   = data.get("endTime", datetime.now().isoformat())

    # ── Score: boolean (0/1) or numeric (0.0–1.0) ────────────────────────
    score: float = 0.0
    for r in data.get("results", []):
        if r.get("type") == "AGGREGATED":
            if "booleanResult" in r:
                score = 1.0 if r["booleanResult"] else 0.0
            elif isinstance(r.get("numericResult"), dict):
                score = float(r["numericResult"].get("value", 0.0))
            break

    # ── Find task conversations (skip metadata-only entries and judge) ────
    conversations = data.get("conversations", [])
    task_convs = [
        c for c in conversations
        if c.get("requests")
        and "Response assessment" not in c.get("id", "")
        and "judge" not in c.get("id", "").lower()
    ]
    if not task_convs:
        return [], "No task conversations with requests found"

    # ── Judge model ───────────────────────────────────────────────────────
    judge_conv = next(
        (c for c in conversations
         if "Response assessment" in c.get("id", "")
         or "judge" in c.get("id", "").lower()),
        None,
    )
    judge_model = ""
    if judge_conv:
        for content in judge_conv.get("requests", [{}])[0].get("contents", []):
            if content.get("role") == "CONTENT_ROLE_ASSISTANT":
                judge_model = content.get("senderName", "")

    # ── Token metrics (whole-task aggregate) ──────────────────────────────
    root_conv = next((c for c in conversations if not c.get("requests")), None)
    metrics = (root_conv or task_convs[0]).get("metrics", {})

    # ── Ground truth from assertion definitions ───────────────────────────
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
    assertions_json = json.dumps(data.get("assertions", []), ensure_ascii=False)

    # ── Shared metadata across all rows from this file ────────────────────
    shared = {
        "task_name":        task_name,
        "task_description": task_ver.get("description", ""),
        "task_definition":  task_ver.get("definition", ""),
        "model_name":       model_slug,
        "ground_truth":     ground_truth,
        "score":            score,
        "reasoning":        reasoning,
        "assertions_json":  assertions_json,
        "judge_model":      judge_model,
        "input_tokens":     metrics.get("inputTokens", 0),
        "output_tokens":    metrics.get("outputTokens", 0),
        "timestamp":        end_time,
    }

    # ── One row per request (subtask) ─────────────────────────────────────
    rows = []
    for conv in task_convs:
        for req in conv.get("requests", []):
            question = ""
            llm_response = ""
            prompt_template = ""
            raw_messages: list[dict] = []

            for content in req.get("contents", []):
                role  = content.get("role", "")
                parts = content.get("parts", [])
                text  = parts[0].get("text", "") if parts else ""
                if role == "CONTENT_ROLE_SYSTEM" and not prompt_template:
                    prompt_template = text
                elif role == "CONTENT_ROLE_USER":
                    if not question:
                        question = text
                    raw_messages.append({"role": "user", "content": text})
                elif role == "CONTENT_ROLE_ASSISTANT":
                    llm_response = text
                    raw_messages.append({"role": "assistant", "content": text})

            if not question or not llm_response:
                continue

            rows.append({
                **shared,
                "question":        question,
                "prompt_template": prompt_template or question,
                "llm_response":    llm_response,
                "messages":        json.dumps(raw_messages, ensure_ascii=False),
            })

    if not rows:
        return [], "No request/response pairs could be extracted"

    return rows, ""


def merge_outputs(
    json_paths: list[Path],
    output_dir: Path,
    deduplicate: bool = True,
    passing_only: bool = True,
    max_pairs_per_question: int = 8,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Parse .run.json files and merge into Format A (SFT) and Format B (preferences).

    passing_only: when True (default), SFT includes only rows with score >= 0.5.
    For boolean tasks (0/1) this keeps only correct responses; for numeric tasks
    it keeps responses scoring at least half-credit.

    max_pairs_per_question: cap on preference pairs per question. Excess pairs
    are sampled deterministically (seeded on task+question).

    Returns (sft_df, pref_df, stats).
    Writes evalflow_sft.csv/.parquet and evalflow_preferences.csv/.parquet to output_dir.
    """
    if not json_paths:
        raise ValueError("No .run.json paths provided")

    rows, skipped = [], []
    for path in json_paths:
        file_rows, reason = parse_run_json(path)
        if not file_rows:
            skipped.append((path.name, reason))
        else:
            rows.extend(file_rows)

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

    sft_raw = raw[raw["score"] >= 0.5].reset_index(drop=True) if passing_only else raw
    sft_df  = _build_sft(sft_raw)
    pref_df = _build_preferences(raw, max_pairs_per_question=max_pairs_per_question)

    output_dir.mkdir(parents=True, exist_ok=True)
    sft_path  = output_dir / SFT_FILENAME
    pref_path = output_dir / PREF_FILENAME
    # Sanitize metadata columns against CSV/spreadsheet formula injection.
    # Content columns (llm_response, question, chosen, rejected, etc.) are left
    # unchanged — prefixing them would corrupt training data.
    _sanitize_metadata(sft_df,  ["task_name", "task_description", "model_name", "judge_model"])
    _sanitize_metadata(pref_df, ["task_name", "chosen_model", "rejected_model"])
    sft_df.to_csv(sft_path,  index=False)
    pref_df.to_csv(pref_path, index=False)

    parquet_written = _write_parquet(sft_df, pref_df, output_dir)

    pref_questions = pref_df["prompt"].nunique() if not pref_df.empty else 0

    stats = {
        "total_rows":             len(sft_df),
        "files_merged":           len(json_paths),
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


# ── CSV injection guard ─────────────────────────────────────────────────────

_FORMULA_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_metadata(df: pd.DataFrame, columns: list[str]) -> None:
    """Prefix formula-starting chars in metadata columns to prevent spreadsheet injection."""
    for col in columns:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: f"'{v}" if isinstance(v, str) and v.startswith(_FORMULA_CHARS) else v
            )


# ── Format A — SFT ──────────────────────────────────────────────────────────

def _build_sft(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    extra   = [c for c in df.columns if c not in SFT_COLUMNS]
    ordered = [c for c in SFT_COLUMNS if c in df.columns] + extra
    return df[ordered]


# ── Format B — Preference pairs ─────────────────────────────────────────────

_MIN_SCORE_DELTA = 0.2  # minimum score difference to consider a meaningful preference


def _build_preferences(raw: pd.DataFrame, max_pairs_per_question: int = 8) -> pd.DataFrame:
    """
    All model pairs per (task, question) where chosen_score - rejected_score >= 0.2.

    Using itertools.combinations to compare every model pair, not just max-vs-min,
    so questions with multiple models at different score levels produce richer signal.
    Pairs are capped at max_pairs_per_question; overflow is sampled deterministically.

    Column names match HuggingFace TRL DPOTrainer: prompt / chosen / rejected.
    chosen_score / rejected_score are included for downstream filtering.
    """
    pairs = []
    for (task_name, question), grp in raw.groupby(["task_name", "question"]):
        if grp["score"].nunique() < 2:
            continue  # all models scored identically — no preference signal

        ground_truth = grp["ground_truth"].iloc[0] if "ground_truth" in grp.columns else ""
        ts = datetime.now().isoformat()

        question_pairs = []
        for a, b in itertools.combinations(grp.itertuples(index=False), 2):
            diff = a.score - b.score
            if abs(diff) < _MIN_SCORE_DELTA:
                continue
            chosen_row   = a if diff > 0 else b
            rejected_row = b if diff > 0 else a
            question_pairs.append({
                "task_name":      task_name,
                "prompt":         question,
                "ground_truth":   ground_truth,
                "chosen":         chosen_row.llm_response,
                "chosen_model":   chosen_row.model_name,
                "chosen_score":   chosen_row.score,
                "rejected":       rejected_row.llm_response,
                "rejected_model": rejected_row.model_name,
                "rejected_score": rejected_row.score,
                "timestamp":      ts,
            })

        if len(question_pairs) > max_pairs_per_question:
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
        sft_df.to_parquet(output_dir / SFT_FILENAME.replace(".csv", ".parquet"),  index=False)
        pref_df.to_parquet(output_dir / PREF_FILENAME.replace(".csv", ".parquet"), index=False)
        return True
    except ImportError:
        return False
