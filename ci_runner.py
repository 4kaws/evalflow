#!/usr/bin/env python3
"""
ci_runner.py — pull all task outputs from a Kaggle benchmark, merge, and publish.

Usage:
    python ci_runner.py \
        --slug  your-username/your-benchmark-name \
        --dataset-slug  your-dataset-slug \
        --dataset-title "Your Dataset Title"
"""

import argparse
import sys
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
    return p.parse_args()


def discover_tasks(api, benchmark_slug: str) -> list[str]:
    """Return all task notebook slugs under a benchmark."""
    # Strategy 1: parent/child API
    try:
        children = api.kernels_list(parent=benchmark_slug, page_size=100)
        if children:
            slugs = [k.ref for k in children]
            print(f"   Found {len(slugs)} task(s) via parent lookup")
            return slugs
    except Exception:
        pass

    # Strategy 2: search by name
    username, name = benchmark_slug.split("/", 1)
    try:
        results = api.kernels_list(user=username, search=name, page_size=50)
        tasks = [k for k in results if name.rstrip("-_") in k.ref.lower()]
        if tasks:
            slugs = [k.ref for k in tasks]
            print(f"   Found {len(slugs)} task(s) via search")
            return slugs
    except Exception:
        pass

    # Strategy 3: treat as single task
    print("   Could not discover child tasks — treating as single-task benchmark")
    return [benchmark_slug]


def pull_task(api, task_slug: str, out_dir: Path) -> list[Path]:
    """Pull .run.json outputs from one task notebook."""
    import shutil
    tmp = out_dir / "_tmp_task"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        api.kernels_output(task_slug, path=str(tmp))
        saved = []
        for run_file in tmp.glob("*.run.json"):
            dest = out_dir / run_file.name
            run_file.rename(dest)
            saved.append(dest)
            print(f"      Saved: {dest.name}")
        return saved
    except Exception as exc:
        print(f"      ❌ Failed: {exc}", file=sys.stderr)
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    args   = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Authenticate ──────────────────────────────────────────────────
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        print("✅ Authenticated with Kaggle API")
    except (SystemExit, Exception) as exc:
        print(f"❌ Auth failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Discover tasks ────────────────────────────────────────────────
    print(f"\n🔍 Discovering tasks under: {args.slug}")
    task_slugs = discover_tasks(api, args.slug)
    print(f"   → {len(task_slugs)} task(s) to pull\n")

    # ── Pull each task ────────────────────────────────────────────────
    all_files:  list[Path] = []
    failed:     list[str]  = []

    for i, task_slug in enumerate(task_slugs, 1):
        print(f"⬇  [{i}/{len(task_slugs)}] {task_slug}")
        files = pull_task(api, task_slug, out_dir)
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
            sft_df, pref_df, stats = merge_outputs(run_files, out_dir)
            print(f"✅ evalflow_sft.csv          — {len(sft_df)} rows")
            print(f"✅ evalflow_preferences.csv  — {len(pref_df)} preference pairs")
            print(f"   Tasks     : {stats['tasks']}")
            print(f"   Models    : {stats['models']}")
            print(f"   Accuracy  : {stats['accuracy']}%")

    # ── Publish ───────────────────────────────────────────────────────
    if args.publish:
        if not args.dataset_slug or not args.dataset_title:
            print("❌ --dataset-slug and --dataset-title required for --publish", file=sys.stderr)
            sys.exit(1)

        import json, os, shutil
        from core.uploader import upload_dataset

        username = os.environ.get("KAGGLE_USERNAME", "")
        staging  = out_dir / "staging" / args.dataset_slug
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

        for csv in [out_dir / "evalflow_sft.csv", out_dir / "evalflow_preferences.csv"]:
            if csv.exists():
                shutil.copy2(csv, staging / csv.name)

        (staging / "dataset-metadata.json").write_text(json.dumps({
            "title":       args.dataset_title,
            "id":          f"{username}/{args.dataset_slug}",
            "licenses":    [{"name": "CC0-1.0"}],
            "description": args.dataset_description,
        }, indent=2))

        print(f"\n🚀 Publishing: {username}/{args.dataset_slug}")
        result = upload_dataset(folder=staging, is_update=args.update, log_cb=print)
        if not result.success:
            print(f"❌ Publish failed: {result.error}", file=sys.stderr)
            sys.exit(1)
        print(f"✅ Live at: {result.url}")


if __name__ == "__main__":
    main()
