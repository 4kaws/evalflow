"""Upload merged dataset to Kaggle Datasets using kagglesdk with Bearer auth."""

from __future__ import annotations

import io
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import requests as _requests


DEFAULT_LICENSE = "CC0-1.0"

_METADATA_FILES = {
    "dataset-metadata.json",
    "datapackage.json",
    "kernel-metadata.json",
    "model-metadata.json",
    "model-instance-metadata.json",
    "README.md",
}


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
    """Download existing dataset version and merge CSVs into staging, deduplicating."""
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


def _upload_file_to_gcs(path: Path, gcs_url: str) -> None:
    """PUT a file to a pre-authenticated GCS resumable upload URL."""
    size = path.stat().st_size
    with open(path, "rb") as fh:
        resp = _requests.put(
            gcs_url,
            data=fh,
            headers={"Content-Length": str(size)},
            timeout=600,
        )
    resp.raise_for_status()


def upload_dataset(
    folder: Path,
    is_update: bool = False,
    append: bool = True,
    log_cb: Optional[Callable[[str], None]] = None,
) -> UploadResult:
    """Upload or update a Kaggle dataset using kagglesdk Bearer auth.

    Bypasses the old `kaggle` CLI package whose authenticate() path
    prefers Basic auth over OAuth, causing 401 on the blob upload endpoint.
    """
    def log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    # ── Credentials ──────────────────────────────────────────────────────
    username = os.environ.get("KAGGLE_USERNAME", "")
    api_key  = os.environ.get("KAGGLE_KEY", "")
    if not username or not api_key:
        try:
            creds_raw = (Path.home() / ".kaggle/kaggle.json").read_text()
            creds_json = json.loads(creds_raw)
            username = username or creds_json.get("username", "")
            api_key  = api_key  or creds_json.get("key", "")
        except Exception:
            pass
    if not username or not api_key:
        return UploadResult(
            success=False,
            error="Credentials not found. Set KAGGLE_USERNAME and KAGGLE_KEY.",
        )

    # ── Build Bearer client ───────────────────────────────────────────────
    from config import config as _cfg
    _cfg.ensure_kaggle_json()
    from core.auth import make_bearer_client
    kag_client, bearer_ok = make_bearer_client(username, api_key, log=log)
    if not bearer_ok:
        return UploadResult(
            success=False,
            error=(
                "OAuth token not available — blob upload requires Bearer auth.\n"
                "Run the setup wizard (w) and complete the OAuth / Kaggle Login step."
            ),
        )

    # ── Read metadata ─────────────────────────────────────────────────────
    meta_path = folder / "dataset-metadata.json"
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as exc:
        return UploadResult(success=False, error=f"Could not read metadata: {exc}")

    dataset_id = meta.get("id", "")
    if "/" not in dataset_id:
        return UploadResult(success=False, error=f"Invalid dataset id: {dataset_id!r}")
    owner, slug = dataset_id.split("/", 1)

    try:
        # ── Optionally fetch + merge existing version ─────────────────────
        if is_update and append:
            try:
                from kaggle.api.kaggle_api_extended import KaggleApi
                _kapi = KaggleApi()
                _kapi.authenticate()
                fetch_and_append_existing(_kapi, owner, slug, folder, log)
            except Exception as exc:
                log(f"   (skipping append — {exc})")

        # ── Upload each file via Blobs API ────────────────────────────────
        from kagglesdk.blobs.types.blob_api_service import ApiStartBlobUploadRequest, ApiBlobType
        from kagglesdk.datasets.types.dataset_api_service import ApiDatasetNewFile

        file_tokens: list[ApiDatasetNewFile] = []
        files_to_upload = [
            p for p in sorted(folder.iterdir())
            if p.is_file() and p.name not in _METADATA_FILES
        ]

        for fpath in files_to_upload:
            log(f"   uploading {fpath.name} ({fpath.stat().st_size // 1024} KB)…")
            blob_req = ApiStartBlobUploadRequest()
            blob_req.type = ApiBlobType.DATASET
            blob_req.name = fpath.name
            blob_req.content_length = fpath.stat().st_size
            blob_resp = kag_client.blobs.blob_api_client.start_blob_upload(blob_req)
            _upload_file_to_gcs(fpath, blob_resp.create_url)
            nf = ApiDatasetNewFile()
            nf.token = blob_resp.token
            file_tokens.append(nf)
            log(f"   + {fpath.name}")

        # ── Create dataset or new version ─────────────────────────────────
        if is_update:
            log(">> Creating new dataset version…")
            from kagglesdk.datasets.types.dataset_api_service import (
                ApiCreateDatasetVersionRequest,
                ApiCreateDatasetVersionRequestBody,
            )
            body = ApiCreateDatasetVersionRequestBody()
            body.version_notes = "Updated via Evalflow"
            body.delete_old_versions = False
            body.files = file_tokens

            ver_req = ApiCreateDatasetVersionRequest()
            ver_req.owner_slug  = owner
            ver_req.dataset_slug = slug
            ver_req.body = body
            kag_client.datasets.dataset_api_client.create_dataset_version(ver_req)
        else:
            log(">> Creating new dataset…")
            from kagglesdk.datasets.types.dataset_api_service import ApiCreateDatasetRequest
            ds_req = ApiCreateDatasetRequest()
            ds_req.owner_slug   = owner
            ds_req.slug         = slug
            ds_req.title        = meta.get("title", slug)
            ds_req.license_name = (meta.get("licenses") or [{}])[0].get("name", DEFAULT_LICENSE)
            ds_req.description  = meta.get("description", "")
            ds_req.is_private   = False
            ds_req.files        = file_tokens
            kag_client.datasets.dataset_api_client.create_dataset(ds_req)

        url = f"https://www.kaggle.com/datasets/{owner}/{slug}"
        log(f"[ok] Dataset published: {url}")
        return UploadResult(success=True, url=url)

    except Exception as exc:
        error_msg = str(exc)
        log(f"[x] Upload failed: {error_msg}")
        return UploadResult(success=False, error=error_msg)
