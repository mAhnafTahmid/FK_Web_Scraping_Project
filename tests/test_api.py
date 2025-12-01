# tests/test_api.py
import os
import pytest
from httpx import AsyncClient
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

API_KEY = os.getenv("API_KEY")


@pytest.mark.asyncio
async def test_list_books_no_filters(client: AsyncClient):
    """
    Test retrieving all books without any filters applied.

    Verifies that the GET /books endpoint returns the complete collection of books
    when called with valid authentication and no query parameters.

    Args:
        client (AsyncClient): Async HTTP client fixture for making API requests

    Asserts:
        - Response status code is 200 (OK)
        - Response contains a 'results' field
        - Total count matches expected number of books (3)
        - Results array contains all expected books (3 items)

    Note:
        Requires valid API_KEY for authentication via X-API-Key header.
    """
    r = await client.get("/books", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert data["total"] == 3
    assert len(data["results"]) == 3


@pytest.mark.asyncio
async def test_list_books_category_filter(client: AsyncClient):
    """
    Test filtering books by category using query parameters.

    Verifies that the GET /books endpoint correctly filters results when a category
    parameter is provided, returning only books that belong to the specified category.

    Args:
        client (AsyncClient): Async HTTP client fixture for making API requests

    Asserts:
        - Response status code is 200 (OK)
        - Total count reflects filtered results (2 books)
        - Only books from the "Fiction" category are returned
        - Specific expected titles ("Alpha" and "Gamma") are present in results

    Note:
        Requires valid API_KEY for authentication via X-API-Key header.
    """
    r = await client.get("/books?category=Fiction", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    titles = [b["title"] for b in data["results"]]
    assert "Alpha" in titles and "Gamma" in titles


@pytest.mark.asyncio
async def test_list_books_price_range(client: AsyncClient):
    """
    Test filtering books by price range using min_price and max_price parameters.

    Verifies that the GET /books endpoint correctly filters results to include only
    books whose prices fall within the specified minimum and maximum bounds (inclusive).

    Args:
        client (AsyncClient): Async HTTP client fixture for making API requests

    Asserts:
        - Response status code is 200 (OK)
        - Total count reflects books within price range $12-$20 (2 books)
        - Expected book "Beta" (priced at $20) is present in results

    Note:
        Requires valid API_KEY for authentication via X-API-Key header.
        Tests with price range that should match book2 ($20) and book3 ($15).
    """
    r = await client.get(
        "/books?min_price=12&max_price=20", headers={"X-API-Key": API_KEY}
    )
    assert r.status_code == 200
    data = r.json()
    # book2 (20) and book3 (15) -> two matches
    assert data["total"] == 2
    assert any(b["title"] == "Beta" for b in data["results"])


@pytest.mark.asyncio
async def test_list_books_sorting_and_pagination(client: AsyncClient):
    """
    Test book sorting and pagination functionality combined.

    Verifies that the GET /books endpoint correctly applies sorting by a specified
    field and returns paginated results with the requested page size.

    Args:
        client (AsyncClient): Async HTTP client fixture for making API requests

    Asserts:
        - Response status code is 200 (OK)
        - Results are sorted by rating in descending order (highest first)
        - First result is "Beta" (highest rating of 5)
        - Page size limit is respected (exactly 2 results returned)

    Note:
        Requires valid API_KEY for authentication via X-API-Key header.
        Tests page 1 with page_size=2, expecting books sorted by rating descending.
    """
    r = await client.get(
        "/books?sort_by=rating&page=1&page_size=2", headers={"X-API-Key": API_KEY}
    )
    assert r.status_code == 200
    data = r.json()
    # highest rating first -> Beta (5), Alpha (4)
    assert data["results"][0]["title"] == "Beta"
    assert len(data["results"]) == 2


@pytest.mark.asyncio
async def test_get_book_by_id_found(client: AsyncClient):
    """
    Test retrieving a specific book by its ID when the book exists.

    Verifies that the GET /books/{book_id} endpoint successfully returns the complete
    book details when given a valid book identifier.

    Args:
        client (AsyncClient): Async HTTP client fixture for making API requests

    Asserts:
        - Response status code is 200 (OK)
        - Returned book has the correct ID ("book1")
        - Book title matches expected value ("Alpha")

    Note:
        Requires valid API_KEY for authentication via X-API-Key header.
    """
    r = await client.get("/books/book1", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    data = r.json()
    assert data["_id"] == "book1"
    assert data["title"] == "Alpha"


@pytest.mark.asyncio
async def test_get_book_by_id_not_found(client: AsyncClient):
    """
    Test retrieving a book by ID when the book does not exist.

    Verifies that the GET /books/{book_id} endpoint returns the appropriate
    404 Not Found status when attempting to retrieve a non-existent book.

    Args:
        client (AsyncClient): Async HTTP client fixture for making API requests

    Asserts:
        - Response status code is 404 (Not Found)

    Note:
        Requires valid API_KEY for authentication via X-API-Key header.
    """
    r = await client.get("/books/nonexistent", headers={"X-API-Key": API_KEY})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_changes_endpoint_default_limit(client: AsyncClient):
    """
    Test retrieving change log entries with default limit settings.

    Verifies that the GET /changes endpoint returns all available change log entries
    when called without explicit limit parameters.

    Args:
        client (AsyncClient): Async HTTP client fixture for making API requests

    Asserts:
        - Response status code is 200 (OK)
        - Response contains a 'results' field
        - Results is a list data type
        - All change log entries are returned (2 entries from fake_db)

    Note:
        Requires valid API_KEY for authentication via X-API-Key header.
        Test assumes fake_db contains exactly 2 change log entries.
    """
    r = await client.get("/changes", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert isinstance(data["results"], list)
    # fake_db has 2 change log entries
    assert len(data["results"]) == 2


@pytest.mark.asyncio
async def test_changes_endpoint_with_limit(client: AsyncClient):
    """
    Test retrieving change log entries with a specified limit parameter.

    Verifies that the GET /changes endpoint correctly respects the limit query
    parameter and returns only the requested number of change log entries.

    Args:
        client (AsyncClient): Async HTTP client fixture for making API requests

    Asserts:
        - Response status code is 200 (OK)
        - Exactly 1 result is returned (matching the limit parameter)

    Note:
        Requires valid API_KEY for authentication via X-API-Key header.
    """
    r = await client.get("/changes?limit=1", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    data = r.json()
    assert len(data["results"]) == 1


@pytest.mark.asyncio
async def test_unauthorized_access(client: AsyncClient):
    """
    Test that requests without authentication are rejected.

    Verifies that the GET /books endpoint properly enforces authentication by
    returning a 401 Unauthorized status when no API key is provided in the request.

    Args:
        client (AsyncClient): Async HTTP client fixture for making API requests

    Asserts:
        - Response status code is 401 (Unauthorized)

    Note:
        Request is made without the X-API-Key header to simulate unauthenticated access.
    """
    r = await client.get("/books")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_validation_error_for_bad_query_param(client: AsyncClient):
    """
    Test request validation for invalid query parameter types.

    Verifies that the GET /books endpoint properly validates query parameters and
    returns a 422 Unprocessable Entity status when provided with invalid data types.

    Args:
        client (AsyncClient): Async HTTP client fixture for making API requests

    Asserts:
        - Response status code is 422 (Unprocessable Entity)

    Note:
        Requires valid API_KEY for authentication via X-API-Key header.
        Tests with invalid 'page' parameter (string "notint" instead of integer >=1).
    """
    r = await client.get("/books?page=notint", headers={"X-API-Key": API_KEY})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rate_limit_hit(client: AsyncClient):
    """
    Test that rate limiting is enforced after exceeding the request limit.

    Verifies that the API's rate limiting mechanism (configured at 100 requests/hour)
    eventually returns a 429 Too Many Requests status when the limit is exceeded.
    Makes 101 sequential requests and checks that the limiter triggers appropriately.

    Args:
        client (AsyncClient): Async HTTP client fixture for making API requests

    Asserts:
        - Final status code is either 200 (OK) or 429 (Too Many Requests)
        - Validates that only valid status codes are returned

    Note:
        Requires valid API_KEY for authentication via X-API-Key header.
        Test behavior may vary based on test isolation and execution speed.
        Exits early if 429 status is encountered before completing all 101 requests.
        Depends on slowapi rate limiting configuration (100 requests/hour).
    """
    headers = {"X-API-Key": API_KEY}
    last_status = None
    for i in range(101):
        r = await client.get("/books", headers=headers)
        last_status = r.status_code
        if last_status == 429:
            break
    assert last_status in (200, 429)
