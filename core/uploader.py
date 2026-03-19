"""Upload merged dataset to Kaggle Datasets using the kaggle SDK."""

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


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


def upload_dataset(
    folder: Path,
    is_update: bool = False,
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
