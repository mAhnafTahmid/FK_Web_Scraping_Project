# scheduler/reporter.py
import os
import json
from datetime import datetime, timezone
from crawler.db import get_db
from utils.alerts import send_alert
import pandas as pd
import logging

logger = logging.getLogger("reporter")
logger.setLevel(logging.INFO)

REPORT_DIR = os.getenv("REPORT_DIR", "./reports")
os.makedirs(REPORT_DIR, exist_ok=True)


async def generate_daily_report():
    """
    Generate a daily change report and send email notification with attachments.

    Queries the database for new changes flagged as 'recent', generates JSON and CSV
    reports, and sends an email alert with the reports attached. Handles both cases
    where changes are detected and where no changes are found.

    Returns:
        None

    Behavior:
        - Retrieves all change_log entries marked as 'recent': 'new'
        - Generates timestamped JSON and CSV files in REPORT_DIR
        - Sends email with appropriate subject based on whether changes were found
        - Cleans MongoDB ObjectId fields by converting to strings for JSON serialization

    Email Cases:
        1. No changes: Sends notification with empty report files
        2. Changes detected: Sends summary with count and details of each change

    Output Files:
        - {REPORT_DIR}/changes_{YYYY-MM-DD}.json
        - {REPORT_DIR}/changes_{YYYY-MM-DD}.csv

    Logs:
        - Info message when reports are generated
        - Info message when no changes are found
        - Info message when email is sent

    Note:
        Uses UTC timezone for all timestamps.
        Email sent via send_alert() function with reports as attachments.
    """
    db = get_db()

    cursor = db.change_log.find({"recent": "new"})
    new_changes = await cursor.to_list(length=None)

    filename_base = f"changes_{datetime.now(timezone.utc).date().isoformat()}"
    json_path = os.path.join(REPORT_DIR, f"{filename_base}.json")
    csv_path = os.path.join(REPORT_DIR, f"{filename_base}.csv")

    if not new_changes:
        no_change_entry = [{"message": "No new changes found in this crawl."}]

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(no_change_entry, f, indent=2)

        pd.DataFrame(no_change_entry).to_csv(csv_path, index=False)

        logger.info("No NEW changes in this crawl. Empty reports generated.")

        subject = "[Crawler] No new changes detected"
        body = (
            "Hello Ahnaf,\n\n"
            "Today's scheduled crawl completed successfully.\n"
            "No new changes were detected.\n\n"
            f"Report generated at: {datetime.now(timezone.utc).isoformat()}Z\n\n"
            "Attached are the JSON and CSV reports for verification.\n"
        )

        send_alert(subject, body, attachments=[json_path, csv_path])
        logger.info("No-change email sent.")

        return

    cleaned = []
    for entry in new_changes:
        entry["_id"] = str(entry["_id"])
        cleaned.append(entry)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2)

    pd.DataFrame(cleaned).to_csv(csv_path, index=False)

    logger.info(f"Generated daily change report: {json_path}, {csv_path}")

    subject = f"[Crawler] {len(cleaned)} new change(s) detected"

    body = (
        f"Hello Ahnaf,\n\n"
        f"The daily crawl detected **{len(cleaned)}** new update(s).\n"
        f"Report generated at: {datetime.now(timezone.utc).isoformat()}Z\n\n"
        f"Summary:\n"
    )

    for entry in cleaned:
        body += (
            f"- Book ID: {entry.get('book_id')} | Type: {entry.get('change_type')}\n"
        )

    body += "\nAttached are the JSON and CSV reports.\n"

    send_alert(subject, body, attachments=[json_path, csv_path])
    logger.info("Alert email (with attachments) sent.")
