import argparse
import logging
import time

from sparkpilot.config import get_settings, validate_runtime_settings
from sparkpilot.db import SessionLocal, init_db
from sparkpilot.services import (
    process_provisioning_once,
    process_cur_reconciliation_once,
    process_reconciler_once,
    process_scheduler_once,
    sync_emr_releases_once,
)

logger = logging.getLogger(__name__)


def _run_forever(worker: str, once: bool) -> None:
    settings = get_settings()
    while True:
        try:
            with SessionLocal() as db:
                if worker == "provisioner":
                    processed = process_provisioning_once(db)
                elif worker == "scheduler":
                    processed = process_scheduler_once(db, limit=settings.queue_batch_size)
                elif worker == "reconciler":
                    processed = process_reconciler_once(db, limit=settings.queue_batch_size)
                elif worker == "emr-release-sync":
                    processed = sync_emr_releases_once(db)
                elif worker == "cur-reconciliation":
                    processed = process_cur_reconciliation_once(db)
                else:
                    raise ValueError(f"Unsupported worker type: {worker}")
            logger.info("[%s] processed=%s", worker, processed)
        except Exception:  # noqa: BLE001 — worker loop must survive unexpected errors; re-raises when once=True
            logger.exception("[%s] iteration failed", worker)
            if once:
                raise
        if once:
            return
        time.sleep(settings.poll_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="SparkPilot worker process")
    parser.add_argument(
        "worker",
        choices=["provisioner", "scheduler", "reconciler", "emr-release-sync", "cur-reconciliation"],
        help="Worker type to run.",
    )
    parser.add_argument("--once", action="store_true", help="Run one iteration and exit.")
    args = parser.parse_args()

    try:
        validate_runtime_settings(get_settings())
    except ValueError as exc:
        raise SystemExit(f"Configuration error: {exc}") from None
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    init_db()
    _run_forever(args.worker, args.once)


if __name__ == "__main__":
    main()
