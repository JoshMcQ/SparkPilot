import argparse
import time

from sparkpilot.config import get_settings
from sparkpilot.db import SessionLocal, init_db
from sparkpilot.services import process_provisioning_once, process_reconciler_once, process_scheduler_once


def _run_forever(worker: str, once: bool) -> None:
    settings = get_settings()
    while True:
        with SessionLocal() as db:
            if worker == "provisioner":
                processed = process_provisioning_once(db)
            elif worker == "scheduler":
                processed = process_scheduler_once(db, limit=settings.queue_batch_size)
            elif worker == "reconciler":
                processed = process_reconciler_once(db, limit=settings.queue_batch_size)
            else:
                raise ValueError(f"Unsupported worker type: {worker}")
        print(f"[{worker}] processed={processed}")
        if once:
            return
        time.sleep(settings.poll_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="SparkPilot worker process")
    parser.add_argument(
        "worker",
        choices=["provisioner", "scheduler", "reconciler"],
        help="Worker type to run.",
    )
    parser.add_argument("--once", action="store_true", help="Run one iteration and exit.")
    args = parser.parse_args()

    init_db()
    _run_forever(args.worker, args.once)


if __name__ == "__main__":
    main()

