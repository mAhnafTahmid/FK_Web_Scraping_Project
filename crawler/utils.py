# crawler/utils.py
import hashlib
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


def compute_hash_for_book(book_dict):
    """
    Generate a deterministic SHA-256 hash for a book's trackable fields.

    Creates a consistent hash value based on specific book attributes to enable
    change detection between crawls. Only fields relevant to content changes are
    included in the hash computation.

    Args:
        book_dict (dict): Dictionary containing book data with keys matching
            the tracked fields

    Returns:
        str: Hexadecimal SHA-256 hash string (64 characters)

    Tracked Fields:
        - title
        - description
        - category
        - price_including_tax
        - price_excluding_tax
        - availability
        - num_reviews
        - image_url
        - rating

    Note:
        Fields are concatenated with "|" delimiter in a fixed order to ensure
        hash consistency. Missing fields default to empty string.
    """

    keys = [
        "title",
        "description",
        "category",
        "price_including_tax",
        "price_excluding_tax",
        "availability",
        "num_reviews",
        "image_url",
        "rating",
    ]
    s = "|".join(str(book_dict.get(k, "")) for k in keys)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def network_retry(**tenacity_kwargs):
    """
    Create a tenacity retry decorator for handling network failures.

    Returns a configured retry decorator with exponential backoff strategy,
    suitable for wrapping functions that make network requests and may
    experience transient failures.

    Args:
        **tenacity_kwargs: Optional keyword arguments
            - attempts (int): Maximum number of retry attempts. Defaults to 3.

    Returns:
        tenacity.Retrying: Configured retry decorator

    Retry Behavior:
        - Stops after specified number of attempts (default: 3)
        - Waits with exponential backoff: min=1s, max=10s, multiplier=1
        - Retries on any Exception type

    Example:
        @network_retry(attempts=5)
        async def fetch_data(url):
            return await client.get(url)
    """
    return retry(
        stop=stop_after_attempt(tenacity_kwargs.get("attempts", 3)),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
