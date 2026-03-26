#!/usr/bin/env python3
"""
monitor.py — check Kaggle benchmarks for new tasks and pull/merge/publish.

Reads watcher config from .evalflow_manifest.json (managed by the TUI Monitor tab).

Usage:
    python monitor.py --all                        # run every saved watcher
    python monitor.py username/benchmark-name      # run one specific watcher

The cron entry installed by the TUI looks like:
    MM HH * * * cd /home/junesdata/evalflow && \\
        /home/junesdata/evalflow/evalflow-venv/bin/python monitor.py --all \\
        >> /home/junesdata/evalflow/monitor.log 2>&1  # evalflow-monitor
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


MANIFEST_FILE = Path(".evalflow_manifest.json")


# ── Manifest ──────────────────────────────────────────────────────────────────

def load_manifest() -> dict:
    # Local file takes priority (TUI / local runs)
    if MANIFEST_FILE.exists():
        try:
            return json.loads(MANIFEST_FILE.read_text())
        except Exception:
            pass
    # Fall back to env var injected by GitHub Actions
    import os
    raw = os.getenv("EVALFLOW_MANIFEST", "").strip()
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}


def save_manifest(manifest: dict) -> None:
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))


# ── Task discovery ────────────────────────────────────────────────────────────

def discover_tasks(api, benchmark_slug: str, kag_client=None) -> list[str]:
    username, slug_name = benchmark_slug.split("/", 1)

    # Strategy 1: benchmark leaderboard API
    if kag_client is not None:
        try:
            from kagglesdk.benchmarks.types.benchmarks_api_service import ApiGetBenchmarkLeaderboardRequest
            req = ApiGetBenchmarkLeaderboardRequest()
            req.owner_slug     = username
            req.benchmark_slug = slug_name
            lb = kag_client.benchmarks.benchmarks_api_client.get_benchmark_leaderboard(req)
            task_slugs: set[str] = set()
            for row in (lb.rows or []):
                for tr in (row.task_results or []):
                    if tr.benchmark_task_slug:
                        short = tr.benchmark_task_slug.rstrip("/").split("/")[-1]
                        task_slugs.add(short)
            if task_slugs:
                return [f"{username}/{s}" for s in sorted(task_slugs)]
        except Exception:
            pass

    # Strategy 2: kernels_list parent
    try:
        children = api.kernels_list(parent=benchmark_slug, page_size=100)
        if children:
            slugs = [k.ref for k in children if k.ref]
            if slugs:
                return slugs
    except Exception:
        pass

    return [benchmark_slug]


# ── Pull one task ─────────────────────────────────────────────────────────────

def pull_task(kag_client, username: str, api_key: str, task_slug: str, out_dir: Path) -> list[Path]:
    import requests
    from kagglesdk.kernels.types.kernels_api_service import ApiListKernelSessionOutputRequest

    owner, kernel_slug = task_slug.split("/", 1)
    all_run_files = []
    page_token = None
    try:
        while True:
            req = ApiListKernelSessionOutputRequest()
            req.user_name   = owner
            req.kernel_slug = kernel_slug
            req.page_size   = 100
            if page_token:
                req.page_token = page_token
            resp = kag_client.kernels.kernels_api_client.list_kernel_session_output(req)
            all_run_files += [f for f in (resp.files or []) if f.file_name.endswith(".run.json")]
            page_token = resp.next_page_token or ""
            if not page_token:
                break
    except Exception as exc:
        exc_str = str(exc)
        if "403" in exc_str:
            print(f"   ⏳ {task_slug}: no accessible runs yet (403) — skipping.", file=sys.stderr)
        else:
            print(f"   [!] Could not list outputs for {task_slug}: {exc_str}", file=sys.stderr)
        return []

    saved = []
    for fi in all_run_files:
        dest = out_dir / fi.file_name
        try:
            r = requests.get(fi.url, auth=(username, api_key), timeout=60)
            r.raise_for_status()
            dest.write_bytes(r.content)
            saved.append(dest)
            print(f"   + {fi.file_name}")
        except Exception as exc:
            print(f"   [!] Download failed for {fi.file_name}: {exc}", file=sys.stderr)
    return saved


# ── Run one watcher ───────────────────────────────────────────────────────────

def run_watcher(slug: str, entry: dict, out_dir: Path, force: bool = False) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    print(f"\n[{now}] Checking: {slug}")

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    import os
    from config import config

    if config.kaggle_username:
        os.environ["KAGGLE_USERNAME"] = config.kaggle_username
    if config.kaggle_key:
        os.environ["KAGGLE_KEY"] = config.kaggle_key

    username = config.kaggle_username
    api_key  = config.kaggle_key
    if not username or not api_key:
        print("❌ KAGGLE_USERNAME and KAGGLE_KEY must be set in .env", file=sys.stderr)
        return

    try:
        from kagglesdk import KaggleClient
        from kaggle.api.kaggle_api_extended import KaggleApi
        kag_client = KaggleClient(username=username, api_token=api_key)
        api = KaggleApi(); api.authenticate()
    except Exception as exc:
        print(f"❌ Auth failed: {exc}", file=sys.stderr)
        return

    current_tasks = discover_tasks(api, slug, kag_client=kag_client)
    print(f"   Found {len(current_tasks)} task(s): {', '.join(current_tasks)}")

    known     = set(entry.get("known_tasks", []))
    new_tasks = current_tasks if force else [t for t in current_tasks if t not in known]

    if not new_tasks:
        print("   ✅ No new tasks.")
        entry["last_checked"] = now
        return

    print(f"   🆕 {len(new_tasks)} new task(s)")

    out_dir.mkdir(parents=True, exist_ok=True)
    all_downloaded: list[Path] = []
    pulled_tasks: set[str] = set()
    for task_slug in new_tasks:
        print(f"\n   Pulling: {task_slug}")
        files = pull_task(kag_client, username, api_key, task_slug, out_dir)
        if files:
            pulled_tasks.add(task_slug)
        all_downloaded.extend(files)

    if not all_downloaded:
        print("   ⚠  No files downloaded.")
        entry["last_checked"] = now
        return

    print(f"\n   ✅ Downloaded {len(all_downloaded)} file(s)")

    from core.merger import discover_outputs, merge_outputs
    run_files = discover_outputs(out_dir)
    sft_df, pref_df, stats = merge_outputs(run_files, out_dir)
    print(f"   evalflow_sft.csv         — {len(sft_df)} rows")
    print(f"   evalflow_preferences.csv — {len(pref_df)} preference pairs")

    if entry.get("publish") and not entry.get("dataset_slug"):
        print("   ⚠  Auto-publish is on but no dataset_slug configured — skipping publish.", file=sys.stderr)
    if entry.get("publish") and entry.get("dataset_slug") and entry.get("dataset_title"):
        from core.uploader import upload_dataset
        ds_slug  = entry["dataset_slug"]
        ds_title = entry["dataset_title"]
        staging  = out_dir / "staging" / ds_slug
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        for csv_name in ("evalflow_sft.csv", "evalflow_preferences.csv"):
            src = out_dir / csv_name
            if src.exists():
                shutil.copy2(src, staging / csv_name)
        (staging / "dataset-metadata.json").write_text(json.dumps({
            "title":    ds_title,
            "id":       f"{username}/{ds_slug}",
            "licenses": [{"name": "CC0-1.0"}],
        }, indent=2))
        print(f"\n   Publishing {username}/{ds_slug} …")
        result = upload_dataset(folder=staging, is_update=True, append=True, log_cb=print)
        if result.success:
            print(f"   ✅ {result.url}")
        else:
            print(f"   ❌ {result.error}", file=sys.stderr)

    # Only mark tasks as known if files were actually pulled (403 = no runs yet → retry)
    entry["known_tasks"]  = list(known | pulled_tasks)
    entry["last_checked"] = now
    entry["last_pull"]    = now


# ── CLI entry point ───────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evalflow monitor")
    p.add_argument("slug", nargs="?", default=None,
                   help="Benchmark slug: username/benchmark-name")
    p.add_argument("--all", dest="run_all", action="store_true",
                   help="Run all watchers in .evalflow_manifest.json")
    p.add_argument("--output-dir", default="outputs")
    p.add_argument("--force", action="store_true",
                   help="Pull all tasks even if already in manifest")
    return p.parse_args()


def main() -> None:
    args    = parse_args()
    out_dir = Path(args.output_dir)

    if args.run_all:
        manifest = load_manifest()
        if not manifest:
            print("No watchers configured. Add one via the TUI Monitor tab.")
            return
        for slug, entry in manifest.items():
            run_watcher(slug, entry, out_dir, force=args.force)
        save_manifest(manifest)
        return

    if not args.slug:
        print("Provide a benchmark slug or use --all")
        return

    manifest = load_manifest()
    entry    = manifest.get(args.slug, {"known_tasks": []})
    run_watcher(args.slug, entry, out_dir, force=args.force)
    manifest[args.slug] = entry
    save_manifest(manifest)


if __name__ == "__main__":
    main()