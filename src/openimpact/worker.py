"""Single-process local worker for persisted OpenImpact analysis tasks.

The API only queues work. This module claims one SQLite-backed task at a time,
so a server restart never turns an accepted request into an unknown result.
"""

from __future__ import annotations

import argparse
import os
import socket
import time
import uuid

from openimpact.api import _run_claimed_analysis_task
from openimpact.storage import claim_next_analysis_task


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def run_once(*, worker_id: str | None = None, lease_seconds: int = 300) -> bool:
    """Claim and execute at most one persisted task; return whether work ran."""
    current_worker = worker_id or default_worker_id()
    task = claim_next_analysis_task(worker_id=current_worker, lease_seconds=lease_seconds)
    if task is None:
        return False
    _run_claimed_analysis_task(task, current_worker)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openimpact-worker", description="运行本机 OpenImpact 分析任务 Worker")
    parser.add_argument("--once", action="store_true", help="最多领取并执行一项任务后退出")
    parser.add_argument("--poll-interval", type=float, default=0.5, help="空队列时的轮询间隔秒数")
    parser.add_argument("--lease-seconds", type=int, default=300, help="任务领取租约秒数")
    args = parser.parse_args(argv)
    if args.poll_interval <= 0 or args.lease_seconds < 1:
        parser.error("poll-interval 必须大于 0，lease-seconds 必须至少为 1")
    worker_id = default_worker_id()
    if args.once:
        run_once(worker_id=worker_id, lease_seconds=args.lease_seconds)
        return 0
    try:
        while True:
            if not run_once(worker_id=worker_id, lease_seconds=args.lease_seconds):
                time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
