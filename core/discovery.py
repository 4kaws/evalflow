"""Shared benchmark task discovery via the Kaggle leaderboard API."""

from __future__ import annotations

from typing import Callable, Optional


def discover_tasks(
    kag_client,
    benchmark_slug: str,
    log: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """
    Return all task slugs for a benchmark via the leaderboard API.

    Returns [] on failure — callers decide the fallback (e.g. treat slug as a
    single task, or show an error to the user).
    """
    def write(msg: str) -> None:
        if log:
            log(msg)

    username, slug_name = benchmark_slug.split("/", 1)
    try:
        from kagglesdk.benchmarks.types.benchmarks_api_service import (
            ApiGetBenchmarkLeaderboardRequest,
        )
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

    return []
