#!/usr/bin/env python3
"""
ci_runner.py — pull all task outputs from a Kaggle benchmark, merge, and publish.

Usage:
    python ci_runner.py \
        --slug  your-username/your-benchmark-name \
        --dataset-slug  your-dataset-slug \
        --dataset-title "Your Dataset Title"

For CI: set KAGGLE_USERNAME, KAGGLE_KEY, and KAGGLE_REFRESH_TOKEN as secrets.
KAGGLE_REFRESH_TOKEN enables Bearer auth so all model runs are fetched.
Get the value from ~/.kaggle/credentials.json after running `kaggle auth login`.
"""
from __future__ import annotations

import argparse
import io
import sys
import time
import zipfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evalflow headless CI runner")
    p.add_argument("--slug", required=True,
        help="Kaggle benchmark slug: username/benchmark-name")
    p.add_argument("--output-dir", default="outputs")
    p.add_argument("--merge",   action="store_true", default=True)
    p.add_argument("--publish", action="store_true", default=False)
    p.add_argument("--update",  action="store_true", default=False)
    p.add_argument("--dataset-slug",        default=None)
    p.add_argument("--dataset-title",       default=None)
    p.add_argument("--dataset-description", default="")
    p.add_argument("--max-pairs", type=int, default=8,
        help="Max DPO preference pairs per question (default: 8)")
    return p.parse_args()


def _api_call_with_retry(call, label: str):
    """Call a zero-arg callable, retrying on HTTP 429 with exponential back-off."""
    delays = [2, 5, 15]
    for delay in delays + [None]:
        try:
            return call()
        except Exception as exc:
            if "429" not in str(exc) or delay is None:
                raise
            time.sleep(delay)


def pull_task(kag_client, task_slug: str, out_dir: Path, bearer_ok: bool = True) -> list[Path]:
    """Download all .run.json outputs for a benchmark task via the Tasks API.

    Returns a list of saved paths (empty if no completed runs exist).
    Falls back to the Kernels API (latest session only) on 403/404.
    """
    from kagglesdk.benchmarks.types.benchmark_tasks_api_service import (
        ApiBenchmarkTaskSlug,
        ApiDownloadBenchmarkTaskRunOutputRequest,
        ApiListBenchmarkTaskRunsRequest,
        BenchmarkTaskRunState,
    )

    owner, slug_name = task_slug.split("/", 1)
    client = kag_client.benchmarks.benchmark_tasks_api_client

    completed_run_ids: list[int] = []
    page_token = ""
    try:
        while True:
            req = ApiListBenchmarkTaskRunsRequest()
            slug_obj = ApiBenchmarkTaskSlug()
            slug_obj.owner_slug = owner
            slug_obj.task_slug  = slug_name
            req.task_slug  = slug_obj
            req.page_size  = 100
            if page_token:
                req.page_token = page_token
            resp = _api_call_with_retry(
                lambda r=req: client.list_benchmark_task_runs(r),
                "list runs",
            )
            for run in resp.runs or []:
                if run.state == BenchmarkTaskRunState.BENCHMARK_TASK_RUN_STATE_COMPLETED:
                    completed_run_ids.append(run.id)
            page_token = resp.next_page_token or ""
            if not page_token:
                break
    except Exception as exc:
        exc_str = str(exc)
        if "403" in exc_str or "404" in exc_str:
            is_404 = "404" in exc_str
            if is_404 and bearer_ok:
                print(
                    "   [!] Tasks API returned 404 — slug is not a registered benchmark task\n"
                    "   or you don't own it. Falling back to Kernels API (latest run only)."
                )
            elif bearer_ok:
                print(
                    "   [!] Tasks API returned 403 despite valid Bearer auth —\n"
                    "   OAuth token may have expired. Re-run the wizard and redo the OAuth step,\n"
                    "   or refresh KAGGLE_REFRESH_TOKEN. Falling back to Kernels API (latest run only)."
                )
            else:
                print("   [!] Tasks API requires OAuth — falling back to Kernels API (latest run only).")
            return _pull_task_kernels(kag_client, task_slug, out_dir)
        print(f"   [x] Failed to list runs: {exc_str}", file=sys.stderr)
        return []

    if not completed_run_ids:
        print("   [!] No completed runs found")
        return []

    print(f"   {len(completed_run_ids)} completed run(s)")
    saved: list[Path] = []
    for run_id in completed_run_ids:
        try:
            dl_req = ApiDownloadBenchmarkTaskRunOutputRequest()
            dl_req.run_id = run_id
            r = _api_call_with_retry(
                lambda req=dl_req: client.download_benchmark_task_run_output(req),
                f"download run {run_id}",
            )
            if not r.ok:
                print(f"   [!] Run {run_id}: HTTP {r.status_code}")
                continue
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            for name in zf.namelist():
                if not name.endswith(".run.json"):
                    continue
                dest = out_dir / Path(name).name
                if not dest.exists():
                    dest.write_bytes(zf.read(name))
                saved.append(dest)
                print(f"   + {name}")
        except Exception as exc:
            print(f"   [!] Failed to download run {run_id}: {exc}", file=sys.stderr)

    return saved


def _pull_task_kernels(kag_client, task_slug: str, out_dir: Path) -> list[Path]:
    """Kernels API fallback — returns only the latest model run."""
    from kagglesdk.kernels.types.kernels_api_service import ApiListKernelSessionOutputRequest

    owner, slug_name = task_slug.split("/", 1)
    req = ApiListKernelSessionOutputRequest()
    req.user_name   = owner
    req.kernel_slug = slug_name
    try:
        resp = kag_client.kernels.kernels_api_client.list_kernel_session_output(req)
    except Exception as exc:
        print(f"   [x] Kernels API failed: {exc}", file=sys.stderr)
        return []

    saved: list[Path] = []
    for f in resp.files or []:
        if not f.file_name.endswith(".run.json"):
            continue
        import requests as _req
        try:
            r = _req.get(f.url, timeout=60)
            r.raise_for_status()
            dest = out_dir / Path(f.file_name).name
            dest.write_bytes(r.content)
            saved.append(dest)
            print(f"   + {f.file_name}")
        except Exception as exc:
            print(f"   [!] Failed to download {f.file_name}: {exc}", file=sys.stderr)
    return saved


def main() -> None:
    args    = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Authenticate ──────────────────────────────────────────────────
    import os
    from dotenv import load_dotenv
    load_dotenv()
    from config import config

    if not config.kaggle_username or not config.kaggle_key:
        print("❌ KAGGLE_USERNAME and KAGGLE_KEY must be set in .env or environment", file=sys.stderr)
        sys.exit(1)

    config.ensure_kaggle_json()

    from core.auth import make_bearer_client
    kag_client, bearer_ok = make_bearer_client(
        config.kaggle_username,
        config.kaggle_key,
        log=print,
    )

    # ── Discover tasks ────────────────────────────────────────────────
    print(f"\n🔍 Discovering tasks under: {args.slug}")
    from core.discovery import discover_tasks
    task_slugs = discover_tasks(kag_client, args.slug, log=print)
    if not task_slugs:
        print(f"   Could not discover tasks — treating as single-task benchmark")
        task_slugs = [args.slug]
    print(f"   → {len(task_slugs)} task(s) to pull\n")

    # ── Pull each task ────────────────────────────────────────────────
    all_files: list[Path] = []
    failed:    list[str]  = []

    for i, task_slug in enumerate(task_slugs, 1):
        if i > 1:
            time.sleep(0.5)
        print(f"⬇  [{i}/{len(task_slugs)}] {task_slug}")
        files = pull_task(kag_client, task_slug, out_dir, bearer_ok=bearer_ok)
        if files:
            all_files.extend(files)
        else:
            failed.append(task_slug)

    print(f"\n✅ Downloaded {len(all_files)} run file(s)")
    if failed:
        print(f"⚠  {len(failed)} task(s) had no output: {', '.join(failed)}")

    # ── Merge ─────────────────────────────────────────────────────────
    if args.merge:
        print("\n🔗 Merging…")
        from core.merger import discover_outputs, merge_outputs
        run_files = discover_outputs(out_dir)
        if not run_files:
            print("⚠  No .run.json files found to merge.")
        else:
            sft_df, pref_df, stats = merge_outputs(
                run_files, out_dir, max_pairs_per_question=args.max_pairs
            )
            print(f"✅ evalflow_sft.csv          — {len(sft_df)} rows (passing only)")
            print(f"✅ evalflow_preferences.csv  — {len(pref_df)} preference pairs (≤{args.max_pairs}/question)")
            if stats.get("parquet_written"):
                print("✅ .parquet variants written")
            print(f"   Tasks     : {stats['tasks']}")
            print(f"   Models    : {stats['models']}")
            print(f"   Accuracy  : {stats['accuracy']}%")

    # ── Publish ───────────────────────────────────────────────────────
    if args.publish:
        if not args.dataset_slug or not args.dataset_title:
            print("❌ --dataset-slug and --dataset-title required for --publish", file=sys.stderr)
            sys.exit(1)

        import json, shutil
        from core.merger import SFT_FILENAME, PREF_FILENAME, row_count
        from core.uploader import upload_dataset, DEFAULT_LICENSE
        from views.publish_view import build_dataset_card

        staging = out_dir / "staging" / args.dataset_slug
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

        sft_path  = out_dir / SFT_FILENAME
        pref_path = out_dir / PREF_FILENAME
        for f in [sft_path, pref_path,
                   sft_path.with_suffix(".parquet"),
                   pref_path.with_suffix(".parquet")]:
            if f.exists():
                shutil.copy2(f, staging / f.name)

        readme = build_dataset_card(
            title=args.dataset_title,
            description=args.dataset_description,
            sft_rows=row_count(sft_path),
            pref_pairs=row_count(pref_path),
            max_pairs_per_question=args.max_pairs,
        )
        (staging / "README.md").write_text(readme, encoding="utf-8")

        (staging / "dataset-metadata.json").write_text(json.dumps({
            "title":       args.dataset_title,
            "id":          f"{config.kaggle_username}/{args.dataset_slug}",
            "licenses":    [{"name": DEFAULT_LICENSE}],
            "description": args.dataset_description,
        }, indent=2))

        print(f"\n🚀 Publishing: {config.kaggle_username}/{args.dataset_slug}")
        result = upload_dataset(folder=staging, is_update=args.update, log_cb=print)
        if not result.success:
            print(f"❌ Publish failed: {result.error}", file=sys.stderr)
            sys.exit(1)
        print(f"✅ Live at: {result.url}")


if __name__ == "__main__":
    main()
