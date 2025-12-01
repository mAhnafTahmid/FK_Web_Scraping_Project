# api/main.py
from fastapi import FastAPI, Depends, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import os
from dotenv import load_dotenv
from .auth import get_api_key
from .rate_limit import register_rate_limit, limiter
from crawler.db import get_db
import logging
from bson import ObjectId

load_dotenv()
API_PORT = int(os.getenv("API_PORT"))

app = FastAPI(title="Books Scraper API", version="1.0")

register_rate_limit(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

logger = logging.getLogger("api")
logger.setLevel(logging.INFO)


def book_doc_to_resp(doc):
    """
    Transform a MongoDB book document into a clean API response dictionary.

    Filters the database document to include only fields intended for API
    responses, excluding internal fields like raw_snapshot_id and content_hash.

    Args:
        doc (dict): MongoDB book document with all fields

    Returns:
        dict: Filtered dictionary containing only public-facing fields:
            - _id
            - title
            - description
            - category
            - price_including_tax
            - price_excluding_tax
            - availability
            - num_reviews
            - image_url
            - rating
            - source_url
            - crawl_timestamp

    Note:
        Returns None for any fields not present in the source document.
        Used to sanitize database documents before returning them in API responses.
    """
    return {
        k: doc.get(k)
        for k in [
            "_id",
            "title",
            "description",
            "category",
            "price_including_tax",
            "price_excluding_tax",
            "availability",
            "num_reviews",
            "image_url",
            "rating",
            "source_url",
            "crawl_timestamp",
        ]
    }


@app.get("/books", dependencies=[Depends(get_api_key)])
@limiter.limit("100/hour")
async def list_books(
    request: Request,
    category: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    rating: Optional[int] = Query(None),
    sort_by: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    """
    List books with optional filtering, sorting, and pagination.

    Retrieves books from the database with support for multiple query parameters
    to filter results by category, price range, and rating. Results can be sorted
    and paginated for efficient data retrieval.

    Args:
        request (Request): FastAPI request object (required for rate limiting)
        category (str, optional): Filter by exact category match
        min_price (float, optional): Minimum price (inclusive) for price_including_tax
        max_price (float, optional): Maximum price (inclusive) for price_including_tax
        rating (int, optional): Filter by exact rating value
        sort_by (str, optional): Sort field - accepts 'rating' (desc), 'price' (asc),
            or 'reviews' (desc)
        page (int): Page number, must be >= 1. Defaults to 1
        page_size (int): Number of results per page, must be 1-200. Defaults to 20

    Returns:
        JSONResponse: Paginated response containing:
            - page (int): Current page number
            - page_size (int): Number of items per page
            - total (int): Total count of matching books
            - results (list[dict]): Array of book objects with public fields

    Rate Limit:
        100 requests per hour per client

    Security:
        Requires valid API key via X-API-Key header

    Query Building:
        - Filters are combined with AND logic
        - Price range uses MongoDB $gte and $lte operators
        - Empty filters are omitted from query

    Sorting Options:
        - 'rating': Descending order (highest first)
        - 'price': Ascending order (lowest first)
        - 'reviews': Descending order (most reviewed first)

    Note:
        Results are transformed via book_doc_to_resp() to exclude internal fields.
        Total count is computed from the filtered query before pagination.
    """
    db = get_db()

    q = {}

    if category:
        q["category"] = category

    if rating:
        q["rating"] = rating

    if min_price is not None or max_price is not None:
        psub = {}
        if min_price is not None:
            psub["$gte"] = min_price
        if max_price is not None:
            psub["$lte"] = max_price
        q["price_including_tax"] = psub

    cursor = db.books.find(q)

    if sort_by:
        if sort_by == "rating":
            cursor = cursor.sort([("rating", -1)])
        elif sort_by == "price":
            cursor = cursor.sort([("price_including_tax", 1)])
        elif sort_by == "reviews":
            cursor = cursor.sort([("num_reviews", -1)])

    total = await db.books.count_documents(q)  # ✔ correct way
    skip = (page - 1) * page_size

    docs = await cursor.skip(skip).limit(page_size).to_list(length=page_size)
    results = [book_doc_to_resp(d) for d in docs]

    return JSONResponse(
        {
            "page": page,
            "page_size": page_size,
            "total": total,
            "results": results,
        }
    )


@app.get("/books/{book_id}", dependencies=[Depends(get_api_key)])
@limiter.limit("100/hour")
async def get_book(request: Request, book_id: str):
    """
    Retrieve a single book by its unique identifier.

    Fetches detailed information for a specific book from the database using
    its ID. Returns a 404 error if the book doesn't exist.

    Args:
        request (Request): FastAPI request object (required for rate limiting)
        book_id (str): The unique identifier of the book to retrieve

    Returns:
        dict: Book data with public-facing fields (transformed via book_doc_to_resp)

    Raises:
        HTTPException: 404 if no book exists with the given book_id

    Rate Limit:
        100 requests per hour per client

    Security:
        Requires valid API key via X-API-Key header

    Note:
        Internal fields like raw_snapshot_id and content_hash are excluded
        from the response.
    """
    db = get_db()
    doc = await db.books.find_one({"_id": book_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Book not found")
    return book_doc_to_resp(doc)


def serialize_change(doc):
    """
    Convert MongoDB ObjectId fields to strings for JSON serialization.

    Transforms ObjectId instances in a change log document to string representation
    to ensure the document can be safely serialized to JSON for API responses.

    Args:
        doc (dict): MongoDB change_log document that may contain ObjectId fields

    Returns:
        dict: The same document with ObjectId fields converted to strings

    Modified Fields:
        - _id: Always converted to string
        - book_id: Converted to string if it's an ObjectId instance

    Note:
        Modifies the document in-place and returns it for convenience.
        Handles cases where book_id might be stored as either string or ObjectId.
    """
    doc["_id"] = str(doc["_id"])
    if "book_id" in doc and isinstance(doc["book_id"], ObjectId):
        doc["book_id"] = str(doc["book_id"])
    return doc


@app.get("/changes", dependencies=[Depends(get_api_key)])
@limiter.limit("100/hour")
async def get_changes(request: Request, limit: int = 100):
    """
    Retrieve recent change log entries.

    Fetches the most recent change log entries marked as 'new', sorted by
    timestamp in descending order (newest first). Useful for monitoring
    recent updates and additions to the book catalog.

    Args:
        request (Request): FastAPI request object (required for rate limiting)
        limit (int): Maximum number of change records to return. Defaults to 100

    Returns:
        dict: Response containing:
            - results (list[dict]): Array of change log entries with serialized
              ObjectId fields, sorted newest to oldest

    Rate Limit:
        100 requests per hour per client

    Security:
        Requires valid API key via X-API-Key header

    Query Behavior:
        - Only returns entries where recent='new'
        - Results sorted by timestamp descending
        - ObjectId fields converted to strings via serialize_change()

    Note:
        Change records are marked as 'new' during crawls and can be marked
        as 'old' by subsequent crawl operations. This endpoint shows only
        the latest batch of detected changes.
    """
    db = get_db()

    docs = (
        await db.change_log.find({"recent": "new"})
        .sort([("timestamp", -1)])
        .limit(limit)
        .to_list(length=limit)
    )

    serialized = [serialize_change(d) for d in docs]
    return {"results": serialized}


# Run uvicorn externally or here
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=API_PORT, reload=True)
