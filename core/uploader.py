"""Upload merged dataset to Kaggle Datasets using the kaggle SDK."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pandas as pd


DEFAULT_LICENSE = "CC0-1.0"


@dataclass
class UploadResult:
    success: bool
    url: str = ""
    error: str = ""


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
        # kaggle v2+ sends blob uploads through a Bearer-only endpoint.
        # If KAGGLE_USERNAME+KEY are set, authenticate() falls back to Basic
        # auth before it checks credentials.json — and the blob endpoint rejects
        # Basic with 401. Inject the OAuth token as KAGGLE_API_TOKEN so the
        # higher-priority _authenticate_with_access_token path wins.
        try:
            from kagglesdk import KaggleClient
            from kagglesdk.kaggle_creds import KaggleCredentials
            _base = KaggleClient(username=username, password=api_key)
            _creds = KaggleCredentials.load(_base)
            if _creds:
                _token = _creds.get_access_token()
                if _token:
                    os.environ["KAGGLE_API_TOKEN"] = _token
        except Exception:
            pass

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
