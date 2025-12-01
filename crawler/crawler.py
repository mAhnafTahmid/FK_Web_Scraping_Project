# crawler/crawler.py
import asyncio
import os
from datetime import datetime, timezone
import re
from bs4 import BeautifulSoup
from httpx import AsyncClient
from .db import (
    insert_snapshot,
    upsert_book,
    get_db,
    mark_all_changes_as_old,
    log_change_entry,
)
from .utils import compute_hash_for_book
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse
import logging

load_dotenv()
BASE_URL = os.getenv("BASE_URL", "https://books.toscrape.com")
CONCURRENCY = int(os.getenv("CRAWL_CONCURRENCY", "10"))
RETRIES = int(os.getenv("CRAWL_RETRIES", "3"))

logger = logging.getLogger("crawler")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)


class Crawler:
    def __init__(self, base_url=BASE_URL, concurrency=CONCURRENCY):
        self.base_url = base_url.rstrip("/")
        self.semaphore = asyncio.Semaphore(concurrency)
        self.client = AsyncClient(timeout=30.0)

    async def close(self):
        """
        Close the HTTP client and release resources.

        Properly shuts down the async HTTP client connection, ensuring all
        resources are cleaned up. Should be called when the crawler instance
        is no longer needed.

        Returns:
            None

        Note:
            This is an async context manager cleanup method. Always call this
            in a finally block or use the crawler in an async with statement
            to ensure proper resource cleanup.
        """
        await self.client.aclose()

    async def fetch(self, url):
        """
        Fetch webpage content with concurrency control and retry logic.

        Performs an HTTP GET request to the specified URL with semaphore-based
        concurrency limiting and automatic retries on failure. Uses exponential
        backoff between retry attempts.

        Args:
            url (str): The URL to fetch

        Returns:
            str: The response text/HTML content from the webpage

        Raises:
            Exception: If all retry attempts fail after RETRIES attempts

        Retry Behavior:
            - Maximum attempts: RETRIES (configured constant)
            - Backoff delay: 1 + (attempt_number * 2) seconds
            - Retries on any exception (network errors, HTTP errors, etc.)

        Note:
            Uses self.semaphore to limit concurrent requests.
            Logs warnings for each failed attempt before retrying.
            Raises HTTP status errors via raise_for_status().
        """
        async with self.semaphore:
            # simple retry wrapper
            for attempt in range(RETRIES):
                try:
                    resp = await self.client.get(url)
                    resp.raise_for_status()
                    return resp.text
                except Exception as e:
                    logger.warning(f"Fetch error {url}: {e} attempt {attempt+1}")
                    await asyncio.sleep(1 + attempt * 2)
            raise Exception(f"Failed to fetch {url} after {RETRIES} tries")

    async def get_all_book_links(self):
        """
        Paginate through the site and collect all book detail URLs.

        Crawls through all catalog pages starting from page-1.html, following
        pagination links until no 'next' button is found. Extracts book detail
        URLs from each page and returns a deduplicated list maintaining original
        order.

        Returns:
            list[str]: Deduplicated list of absolute book detail URLs in order
                of discovery

        Process:
            1. Starts at {base_url}/catalogue/page-1.html
            2. Extracts all book links from article.product_pod h3 a elements
            3. Converts relative URLs to absolute URLs
            4. Follows li.next a pagination link to next page
            5. Repeats until no next button exists
            6. Deduplicates while preserving order

        Logs:
            - Info message for each page being processed

        Note:
            Handles relative book paths (e.g., '../../../book.html') by
            resolving them against the current page URL.
        """
        page_url = f"{self.base_url}/catalogue/page-1.html"
        book_links = []
        while True:
            logger.info(f"Listing page: {page_url}")
            html = await self.fetch(page_url)
            soup = BeautifulSoup(html, "lxml")
            articles = soup.select("article.product_pod h3 a")
            for a in articles:
                rel = a.get("href")
                book_url = urljoin(page_url, rel)
                book_links.append(book_url)
            next_el = soup.select_one("li.next a")
            if next_el and next_el.get("href"):
                page_url = urljoin(page_url, next_el.get("href"))
            else:
                break
        seen = set()
        uniq = []
        for u in book_links:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        return uniq

    def parse_rating(self, soup):
        """
        Extract the numeric rating from a book's star-rating element.

        Parses the CSS class of the star-rating element to determine the
        book's rating value, converting textual rating words to numeric values.

        Args:
            soup (BeautifulSoup): Parsed HTML of the book detail page

        Returns:
            int or None: Rating value between 1-5, or None if rating not found

        Rating Mapping:
            - "One" -> 1
            - "Two" -> 2
            - "Three" -> 3
            - "Four" -> 4
            - "Five" -> 5

        Note:
            Looks for element with class "star-rating" and checks its additional
            class names for rating words (e.g., class="star-rating Three").
        """
        rating_cls = soup.select_one(".star-rating")
        if rating_cls:
            classes = rating_cls.get("class", [])
            mapping = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
            for c in classes:
                if c in mapping:
                    return mapping[c]
        return None

    def parse_book(self, html, url):
        """
        Parse book details from a book detail page HTML.

        Extracts comprehensive book information including title, description, pricing,
        availability, ratings, and metadata from the page HTML. Generates a unique ID
        and content hash for change detection.

        Args:
            html (str): Raw HTML content of the book detail page
            url (str): Source URL of the book page (used for ID generation and image URLs)

        Returns:
            tuple: (book_data_dict, html)
                - book_data_dict (dict): Parsed book information with fields:
                    - _id: Unique identifier derived from URL path
                    - title: Book title from h1
                    - description: Book description from product_description section
                    - category: Category from breadcrumb (3rd item)
                    - price_including_tax: Float price with tax
                    - price_excluding_tax: Float price without tax
                    - availability: Stock status text
                    - num_reviews: Integer count of reviews
                    - image_url: Absolute URL to book cover image
                    - rating: Integer rating 1-5 (or None)
                    - source_url: Original page URL
                    - crawl_timestamp: ISO 8601 UTC timestamp with 'Z' suffix
                    - content_hash: SHA-256 hash of trackable fields
                - html (str): Original HTML (returned for potential caching)

        Note:
            - Book ID extracted from second-to-last path segment in URL
            - Prices parsed by removing non-numeric/decimal characters
            - Image URL resolved to absolute path using urljoin
            - Multiple image selectors attempted (.carousel, #product_gallery, .item.active)
        """
        soup = BeautifulSoup(html, "lxml")
        product = soup.select_one(".product_page")
        title = product.select_one("h1").get_text(strip=True) if product else None
        desc = None
        desc_header = soup.find(id="product_description")
        if desc_header:
            desc_p = desc_header.find_next_sibling("p")
            if desc_p:
                desc = desc_p.get_text(strip=True)
        category = None
        crumbs = soup.select("ul.breadcrumb li a")
        if len(crumbs) >= 3:
            category = crumbs[2].get_text(strip=True)
        table = {}
        for tr in soup.select("table.table.table-striped tr"):
            th = tr.select_one("th").get_text(strip=True)
            td = tr.select_one("td").get_text(strip=True)
            table[th] = td

        def money_to_float(s):
            if not s:
                return None
            m = re.sub(r"[^0-9\.]", "", s)
            try:
                return float(m)
            except:
                return None

        price_incl = money_to_float(table.get("Price (incl. tax)"))
        price_excl = money_to_float(table.get("Price (excl. tax)"))
        availability = table.get("Availability")
        num_reviews = int(table.get("Number of reviews", "0"))
        img = (
            soup.select_one(".carousel img")
            or soup.select_one("#product_gallery img")
            or soup.select_one(".item.active img")
        )
        image_url = urljoin(url, img.get("src")) if img else None
        rating = self.parse_rating(soup)
        parsed = urlparse(url)
        book_id = parsed.path.rstrip("/").split("/")[-2] if parsed.path else url
        data = {
            "_id": book_id,
            "title": title,
            "description": desc,
            "category": category,
            "price_including_tax": price_incl,
            "price_excluding_tax": price_excl,
            "availability": availability,
            "num_reviews": num_reviews,
            "image_url": image_url,
            "rating": rating,
            "source_url": url,
            "crawl_timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }
        data["content_hash"] = compute_hash_for_book(data)
        return data, html

    async def process_book(self, url):
        """
        Fetch, parse, and process a single book's data with change detection.

        Retrieves book details from the given URL, compares against existing database
        records, and handles three scenarios: no changes, updates, or new book insertion.
        Creates snapshots and change log entries as needed.

        Args:
            url (str): The book detail page URL to process

        Returns:
            dict or None: Change record if the book was new or updated, None if
                no changes were detected or if processing failed

        Processing Logic:
            CASE 1 - Existing Book:
                - Checks content hash for changes
                - If unchanged: Returns None (no action)
                - If changed: Computes field-level diff, creates snapshot,
                  updates book, logs change with field details

            CASE 2 - New Book:
                - Creates initial snapshot
                - Inserts book into database
                - Logs 'new' change record

        Change Record Structure:
            {
                'book_id': str,
                'change_type': 'updated' or 'new',
                'recent': 'new',
                'timestamp': ISO 8601 UTC with 'Z',
                'field_changes': dict (for updates only)
            }

        Logs:
            - Info when no changes detected
            - Info when book updated (with changed field names)
            - Info when new book inserted
            - Exception details on processing failure

        Note:
            Skips 'raw_snapshot_id' and 'content_hash' fields when computing diffs.
            All timestamps use UTC with 'Z' suffix.
            Returns None on any exception (errors are logged).
        """
        try:
            html = await self.fetch(url)
            book_data, snapshot_html = self.parse_book(html, url)

            db = get_db()
            existing = await db.books.find_one({"_id": book_data["_id"]})

            if existing:
                if existing.get("content_hash") == book_data["content_hash"]:
                    logger.info(
                        f"No changes for book {book_data['_id']} (content hash matched)"
                    )
                    return None

                changed_fields = {}
                for key, new_val in book_data.items():
                    old_val = existing.get(key)
                    if key == "raw_snapshot_id" or key == "content_hash":
                        continue
                    if old_val != new_val:
                        changed_fields[key] = {"old": old_val, "new": new_val}

                snap = {
                    "source_url": url,
                    "html": snapshot_html,
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                }
                snap_id = await insert_snapshot(snap)
                book_data["raw_snapshot_id"] = snap_id

                # Update book in DB
                await upsert_book(book_data)

                # Log the update
                change_record = {
                    "book_id": book_data["_id"],
                    "change_type": "updated",
                    "recent": "new",
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "field_changes": changed_fields,
                }
                await db.change_log.insert_one(change_record)

                logger.info(
                    f"Updated book {book_data['_id']}: fields changed {list(changed_fields.keys())}"
                )
                return change_record

            else:
                # Snapshot for new book
                snap = {
                    "source_url": url,
                    "html": snapshot_html,
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                }
                snap_id = await insert_snapshot(snap)
                book_data["raw_snapshot_id"] = snap_id

                # Save the new book
                await upsert_book(book_data)

                # Log a simple "new" change record
                change_record = await log_change_entry(book_data["_id"], "new")
                logger.info(f"Inserted new book {book_data['_id']}")
                return change_record

        except Exception as e:
            logger.exception(f"Failed process book {url}: {e}")
            return None

    async def run(self, resume=False):
        """
        Execute a complete crawl of all books and detect changes.

        Performs a full site crawl by discovering all book URLs, processing each book
        concurrently, and tracking changes. Marks previous change log entries as old
        before starting to distinguish new changes from historical ones.

        Args:
            resume (bool, optional): Reserved for future resume functionality.
                Currently unused. Defaults to False.

        Returns:
            list[dict]: List of change records (new or updated books) detected
                during this crawl run. Empty list if no changes found.

        Process:
            1. Marks all existing change_log entries as 'old'
            2. Discovers all book detail page URLs via pagination
            3. Processes all books concurrently using asyncio.gather
            4. Filters out books with no changes (None results)
            5. Returns only the changes detected in this run

        Logs:
            - Info message with total count of book links found

        Note:
            Each book is processed independently and concurrently for performance.
            Failed book processing returns None and is filtered from results.
            Change records are marked as 'recent': 'new' in process_book().
        """
        await mark_all_changes_as_old()

        book_links = await self.get_all_book_links()
        logger.info(f"Found {len(book_links)} book links")

        tasks = [self.process_book(u) for u in book_links]
        results = await asyncio.gather(*tasks)

        changes = [r for r in results if r is not None]
        return changes


# convenience script
async def main():
    c = Crawler()
    try:
        await c.run()
    finally:
        await c.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
