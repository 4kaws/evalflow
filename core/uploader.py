"""Upload merged dataset to Kaggle Datasets using the kaggle SDK."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pandas as pd


@dataclass
class UploadConfig:
    title: str
    slug: str          # e.g. "my-benchmark-results"
    description: str
    license: str = "CC0-1.0"
    public: bool = True


@dataclass
class UploadResult:
    success: bool
    url: str = ""
    error: str = ""


def prepare_dataset_folder(
    merged_csv: Path,
    config: UploadConfig,
    username: str,
    staging_dir: Path = Path("outputs/staging"),
) -> Path:
    """
    Build the Kaggle-expected folder structure:
        <staging_dir>/<slug>/
            <data>.csv
            dataset-metadata.json
    """
    folder = staging_dir / config.slug
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    # Copy CSV
    shutil.copy2(merged_csv, folder / merged_csv.name)

    # Write metadata
    metadata = {
        "title": config.title,
        "id": f"{username}/{config.slug}",
        "licenses": [{"name": config.license}],
        "description": config.description,
    }
    with open(folder / "dataset-metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    return folder


def fetch_and_append_existing(
    api,
    username: str,
    slug: str,
    staging: Path,
    log: Callable[[str], None],
) -> None:
    """
    Download the current version of username/slug from Kaggle, then concatenate
    its evalflow_sft.csv and evalflow_preferences.csv with the files already in
    `staging`, deduplicating in place.  Overwrites the files in staging.
    Silently skips if the dataset doesn't exist yet or download fails.
    """
    with tempfile.TemporaryDirectory() as tmp:
        try:
            log(f">> Fetching existing dataset {username}/{slug} …")
            api.dataset_download_files(
                dataset=f"{username}/{slug}",
                path=tmp,
                unzip=True,
                quiet=True,
            )
        except Exception as exc:
            log(f"   (could not fetch existing data — treating as new: {exc})")
            return

        for fname in ("evalflow_sft.csv", "evalflow_preferences.csv"):
            old_path = Path(tmp) / fname
            new_path = staging / fname
            if not old_path.exists() or not new_path.exists():
                continue
            try:
                old_df = pd.read_csv(old_path)
                new_df = pd.read_csv(new_path)
                combined = pd.concat([old_df, new_df], ignore_index=True)
                dedup_cols = (
                    ["task_name", "model_name", "question", "llm_response"]
                    if fname == "evalflow_sft.csv"
                    else ["task_name", "prompt", "chosen_model", "rejected_model"]
                )
                existing_dedup = [c for c in dedup_cols if c in combined.columns]
                if existing_dedup:
                    combined = combined.drop_duplicates(subset=existing_dedup, keep="last")
                combined.to_csv(new_path, index=False)
                log(f"   + merged {fname}: {len(old_df)} existing + {len(new_df)} new = {len(combined)} rows")
            except Exception as exc:
                log(f"   [!] Could not merge {fname}: {exc}")


def upload_dataset(
    folder: Path,
    is_update: bool = False,
    append: bool = True,
    log_cb: Optional[Callable[[str], None]] = None,
) -> UploadResult:
    """
    Upload or update a Kaggle dataset.
    Requires KAGGLE_USERNAME and KAGGLE_KEY env vars (or ~/.kaggle/kaggle.json).
    """
    def log(msg: str):
        if log_cb:
            log_cb(msg)

    # ── Read credentials ─────────────────────────────────────────────────
    username = os.environ.get("KAGGLE_USERNAME", "")
    api_key  = os.environ.get("KAGGLE_KEY", "")
    if not username or not api_key:
        try:
            import json as _json, pathlib as _pl
            creds = _json.loads((_pl.Path.home() / ".kaggle/kaggle.json").read_text())
            username = username or creds.get("username", "")
            api_key  = api_key  or creds.get("key", "")
        except Exception:
            pass
    if not username or not api_key:
        return UploadResult(
            success=False,
            error="Credentials not found. Set KAGGLE_USERNAME and KAGGLE_KEY.",
        )
    log("[ok] Authenticated with Kaggle API")

    # ── Read metadata ─────────────────────────────────────────────────────
    meta_path = folder / "dataset-metadata.json"
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except Exception as exc:
        return UploadResult(success=False, error=f"Could not read metadata: {exc}")

    dataset_id = meta.get("id", "")
    if "/" not in dataset_id:
        return UploadResult(success=False, error=f"Invalid dataset id: {dataset_id!r}")
    owner, slug = dataset_id.split("/", 1)

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()

        # ── Optionally append existing data ──────────────────────────────
        if is_update and append:
            try:
                fetch_and_append_existing(api, owner, slug, folder, log)
            except Exception as exc:
                log(f"   (skipping append — {exc})")

        # ── Create version or new dataset ─────────────────────────────────
        if is_update:
            log(">> Creating new dataset version…")
            api.dataset_create_version(
                folder=str(folder),
                version_notes="Updated via Evalflow",
                convert_to_csv=False,
                delete_old_versions=False,
                quiet=True,
            )
        else:
            log(">> Creating new dataset…")
            api.dataset_create_new(
                folder=str(folder),
                public=True,
                convert_to_csv=False,
                dir_mode="zip",
                quiet=True,
            )

        url = f"https://www.kaggle.com/datasets/{owner}/{slug}"
        log(f"[ok] Dataset published: {url}")
        return UploadResult(success=True, url=url)

    except Exception as exc:
        error_msg = str(exc)
        log(f"[x] Upload failed: {error_msg}")
        return UploadResult(success=False, error=error_msg)
