"""APScheduler wrapper for periodic scraping."""

import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from config import SCRAPE_INTERVAL_MINUTES

logger = logging.getLogger(__name__)


def _scrape_job():
    """Job function called by scheduler."""
    from scraper import scrape_all, _post_scrape_enrich
    logger.info("=== Scheduled scrape starting ===")
    try:
        changes = scrape_all()
        total = len(changes)
        new = sum(1 for c in changes if c.change_type == "new")
        restocks = sum(1 for c in changes if c.change_type == "restock")
        logger.info(
            f"=== Scheduled scrape done. {total} changes "
            f"({new} new, {restocks} restocks) ==="
        )
        if new > 0:
            _post_scrape_enrich(changes)
    except Exception as e:
        logger.error(f"Scheduled scrape failed: {e}")


def run_scheduler():
    """Start the blocking scheduler."""
    scheduler = BlockingScheduler()
    scheduler.add_job(
        _scrape_job,
        "interval",
        minutes=SCRAPE_INTERVAL_MINUTES,
        id="figure_scraper",
        name="Figure Scraper",
    )

    def shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info(
        f"Scheduler started. Scraping every {SCRAPE_INTERVAL_MINUTES} minutes. "
        "Press Ctrl+C to stop."
    )
    # Run immediately on start, then schedule
    _scrape_job()
    scheduler.start()
