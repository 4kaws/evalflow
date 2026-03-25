"""Upload merged dataset to Kaggle Datasets using the kaggle SDK."""

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
                    else ["task_name", "question", "chosen_model", "rejected_model"]
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

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        log("✅ Authenticated with Kaggle API")
    except ImportError:
        return UploadResult(
            success=False,
            error="kaggle package not installed. Run: pip install kaggle",
        )
    except (SystemExit, Exception) as exc:
        return UploadResult(
            success=False,
            error=f"Auth failed: {exc}\nMake sure KAGGLE_USERNAME and KAGGLE_KEY are set.",
        )

    try:
        if is_update and append:
            meta_path = folder / "dataset-metadata.json"
            with open(meta_path) as f:
                meta = json.load(f)
            owner, slug = meta.get("id", "/").split("/", 1)
            fetch_and_append_existing(api, owner, slug, folder, log)

        if is_update:
            log("📤 Updating existing dataset…")
            api.dataset_create_version(
                folder=str(folder),
                version_notes="Updated via Evalflow",
                convert_to_csv=False,
                delete_old_versions=False,
            )
        else:
            log("📤 Creating new dataset…")
            api.dataset_create_new(
                folder=str(folder),
                convert_to_csv=False,
                public=True,
                quiet=False,
            )

        # Read slug to build URL
        meta_path = folder / "dataset-metadata.json"
        with open(meta_path) as f:
            meta = json.load(f)
        dataset_id = meta.get("id", "")
        url = f"https://www.kaggle.com/datasets/{dataset_id}" if dataset_id else "https://www.kaggle.com/datasets"

        log(f"✅ Dataset published: {url}")
        return UploadResult(success=True, url=url)

    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        log(f"❌ Upload failed: {error_msg}")
        return UploadResult(success=False, error=error_msg)
