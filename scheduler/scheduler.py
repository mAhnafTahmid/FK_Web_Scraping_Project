# scheduler/scheduler.py
import asyncio
from datetime import datetime, timezone
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from crawler.crawler import Crawler
from scheduler.reporter import generate_daily_report


logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(handler)


async def scheduled_crawl():
    """
    Execute a scheduled web crawl and generate a daily report.

    Performs a complete crawl cycle using the Crawler instance, detects changes
    in the scraped data, and triggers report generation based on the findings.
    Ensures proper cleanup of the crawler resources regardless of success or failure.

    Returns:
        None

    Logs:
        - Info message when crawl starts
        - Info message with change count when crawl completes

    Note:
        The crawler is always closed in the finally block to prevent resource leaks.
        Report generation is triggered after successful crawl completion.
    """
    logger.info("Starting scheduled crawl")
    c = Crawler()
    try:
        changes = await c.run()
        logger.info(f"Scheduled crawl finished, {len(changes)} changes detected")
        await generate_daily_report()
    finally:
        await c.close()


async def async_main():
    """
    Initialize and run the asynchronous scheduler for periodic crawl jobs.

    Sets up an APScheduler AsyncIOScheduler that executes the scheduled_crawl
    function at regular intervals. The scheduler runs continuously until the
    program is terminated.

    Returns:
        None (runs indefinitely)

    Configuration:
        - Job: scheduled_crawl
        - Trigger: interval-based (every 10 minutes)
        - Job ID: "test_crawl"

    Logs:
        - Info message when scheduler starts

    Note:
        Uses asyncio.Event().wait() to keep the event loop running indefinitely.
        The function will block until the program receives a termination signal.
        Adjust the interval or switch to cron trigger for production scheduling.
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_crawl,
        "interval",
        minutes=10,
        id="test_crawl",
    )

    scheduler.start()
    logger.info("Scheduler started (every 24 hrs)")
    # Keep program running forever
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(async_main())
