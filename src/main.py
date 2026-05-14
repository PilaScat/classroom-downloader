import logging
import os
import sys
import time

import schedule

from auth import authenticate, build_services
from sync import Syncer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL_MINUTES", "60"))


def run_sync():
    logger.info("Starting sync...")
    try:
        classroom_svc, drive_svc = build_services()
        Syncer(classroom_svc, drive_svc).sync()
    except Exception:
        logger.exception("Sync failed")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        authenticate()
        return

    logger.info("Classroom Downloader started — sync every %d minute(s).", SYNC_INTERVAL)
    run_sync()  # immediate first run

    schedule.every(SYNC_INTERVAL).minutes.do(run_sync)
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
