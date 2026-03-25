"""
Merge multiple benchmark .run.json files into two publication-ready formats:

  Format A — SFT-ready  (evalflow_sft.csv)
      One row per model response. Includes the full conversation, per-assertion
      reasoning, token metrics, and timestamps.

  Format B — Preference pairs  (evalflow_preferences.csv)
      One row per question where at least one model passed AND one failed.
      Provides (chosen_response, chosen_model, rejected_response, rejected_model)
      pairs directly usable in RLHF / DPO pipelines.
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


# ── Column definitions ──────────────────────────────────────────────────────

SFT_COLUMNS = [
    "task_name",
    "model_name",
    "question",
    "llm_response",
    "messages",
    "score",
    "reasoning",
    "judge_model",
    "input_tokens",
    "output_tokens",
    "timestamp",
]

PREF_COLUMNS = [
    "task_name",
    "question",
    "chosen_response",
    "chosen_model",
    "rejected_response",
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

    task_name  = data.get("taskVersion", {}).get("name", "")
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

    # Walk all requests in the conversation, not just the first,
    # so multi-turn tasks from other users are handled correctly
    question     = ""
    llm_response = ""
    raw_messages = []

    for req in main_conv.get("requests", []):
        for content in req.get("contents", []):
            role  = content.get("role", "")
            parts = content.get("parts", [])
            text  = parts[0].get("text", "") if parts else ""
            if role == "CONTENT_ROLE_USER" and not question:
                question = text
                raw_messages.append({"role": "user", "content": text})
            elif role == "CONTENT_ROLE_ASSISTANT" and not llm_response:
                llm_response = text
                raw_messages.append({"role": "assistant", "content": text})

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

    # ── Reasoning from failed assertions ──────────────────────────────────
    failed = [
        a.get("expectation", "")
        for a in data.get("assertions", [])
        if a.get("status") != "BENCHMARK_TASK_RUN_ASSERTION_STATUS_PASSED"
    ]
    reasoning = " | ".join(failed) if failed else ""

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
        "task_name":    task_name,
        "model_name":   model_slug,
        "question":     question,
        "llm_response": llm_response,
        "messages":     json.dumps(raw_messages, ensure_ascii=False),
        "score":        score,
        "reasoning":    reasoning,
        "judge_model":  judge_model,
        "input_tokens": metrics.get("inputTokens", 0),
        "output_tokens": metrics.get("outputTokens", 0),
        "timestamp":    end_time,
    }, ""


def merge_outputs(
    json_paths: list[Path],
    output_dir: Path,
    deduplicate: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Parse .run.json files and merge into Format A (SFT) and Format B (preferences).

    Returns (sft_df, pref_df, stats).
    Writes evalflow_sft.csv and evalflow_preferences.csv to output_dir.
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

    sft_df  = _build_sft(raw)
    pref_df = _build_preferences(raw)

    output_dir.mkdir(parents=True, exist_ok=True)
    sft_path  = output_dir / "evalflow_sft.csv"
    pref_path = output_dir / "evalflow_preferences.csv"
    sft_df.to_csv(sft_path,  index=False)
    pref_df.to_csv(pref_path, index=False)

    pref_questions = pref_df["question"].nunique() if not pref_df.empty else 0

    stats = {
        "total_rows":         len(sft_df),
        "files_merged":       len(rows),
        "files_skipped":      len(skipped),
        "duplicates_removed": dupes_removed,
        "models":             raw["model_name"].nunique(),
        "tasks":              raw["task_name"].nunique(),
        "accuracy":           round(raw["score"].mean() * 100, 1),
        "preference_pairs":   len(pref_df),
        "pref_questions":     pref_questions,
        "sft_path":           str(sft_path),
        "pref_path":          str(pref_path),
        "skipped_details":    skipped,
    }

    return sft_df, pref_df, stats


# ── Format A — SFT ──────────────────────────────────────────────────────────

def _build_sft(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    extra   = [c for c in df.columns if c not in SFT_COLUMNS]
    ordered = [c for c in SFT_COLUMNS if c in df.columns] + extra
    return df[ordered]


# ── Format B — Preference pairs ─────────────────────────────────────────────

def _build_preferences(raw: pd.DataFrame) -> pd.DataFrame:
    pairs = []
    for (task_name, question), grp in raw.groupby(["task_name", "question"]):
        passed = grp[grp["score"] == 1]
        failed = grp[grp["score"] == 0]
        if passed.empty or failed.empty:
            continue

        chosen_row   = passed.loc[passed["llm_response"].str.len().idxmax()]
        rejected_row = failed.loc[failed["llm_response"].str.len().idxmin()]

        pairs.append({
            "task_name":         task_name,
            "question":          question,
            "chosen_response":   chosen_row["llm_response"],
            "chosen_model":      chosen_row["model_name"],
            "rejected_response": rejected_row["llm_response"],
            "rejected_model":    rejected_row["model_name"],
            "timestamp":         datetime.now().isoformat(),
        })

    if not pairs:
        return pd.DataFrame(columns=PREF_COLUMNS)
    df = pd.DataFrame(pairs)
    return df[[c for c in PREF_COLUMNS if c in df.columns]]
