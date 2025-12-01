# tests/conftest.py
import sys
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from bson import ObjectId
import pytest
from typing import List, Dict, Any
from httpx import ASGITransport, AsyncClient
from fastapi import Request, HTTPException

from api.main import app, get_api_key


class FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = list(docs)
        self._skip = 0
        self._limit = None

    def sort(self, order):
        """
        Sort the documents in the cursor by a specified field and direction.

        Simulates MongoDB/Motor's sort() functionality on an in-memory
        list of documents.

        Args:
            order (list[tuple]): A list of (field, direction) tuples, e.g.
                [("field_name", 1)] for ascending or [("field_name", -1)]
                for descending.

        Returns:
            FakeCursor: The same cursor instance to allow method chaining.

        Behavior:
            - Sorts the internal _docs list in-place.
            - Uses the field value as the key; missing fields are treated as None.
            - Ascending order if direction >= 0, descending if direction < 0.
            - Only the first tuple in the order list is used; additional
              sort criteria are ignored.
        """

        field, direction = order[0]
        self._docs.sort(key=lambda d: d.get(field, None), reverse=(direction < 0))
        return self

    def skip(self, n: int):
        """
        Apply a skip to the cursor, offsetting the starting index of results.

        Mimics MongoDB/Motor's skip() behavior by ignoring the first `n`
        documents in the result set when to_list() is called.

        Args:
            n (int): Number of documents to skip from the beginning.

        Returns:
            FakeCursor: The same cursor instance, enabling method chaining.

        Behavior:
            - Stores the skip value internally.
            - When used alongside limit(), the final slice is computed as:
                  docs[skip : skip + limit]
            - Overwrites any previously set skip value.
        """

        self._skip = n
        return self

    def limit(self, n: int):
        """
        Apply a limit to the number of documents returned by the cursor.

        Mimics Motor/MongoDB's limit() behavior by restricting how many
        documents can be fetched when to_list() is called.

        Args:
            n (int): Maximum number of documents to return.

        Returns:
            FakeCursor: The same cursor instance, allowing method chaining.

        Behavior:
            - Stores the limit value internally.
            - When to_list() is invoked, only the first `n` documents after
              any applied skip() will be returned.
            - Overwrites any previously set limit.
        """

        self._limit = n
        return self

    async def to_list(self, length: int):
        """
        Convert the cursor results into a list of documents.

        Simulates the behavior of Motor's to_list() by returning a sliced
        portion of the in-memory documents based on any applied skip() and
        limit() operations.

        Args:
            length (int): Unused placeholder parameter included for API
                compatibility with Motor. The returned list size is determined
                solely by skip() and limit(), not by this argument.

        Returns:
            list[dict]: A list of document copies from the cursor, sliced
            according to:
                - skip(): starting index
                - limit(): maximum number of returned documents (if set)

        Behavior:
            - Returns deep copies (dict(d)) so external modifications do not
              affect stored documents.
            - If no limit was applied, all documents after skip() are returned.
            - Ignores the `length` argument entirely.

        Note:
            This is a simplified mock implementation used for testing and does
            not enforce any asynchronous I/O or Motor-specific constraints.
        """

        start = self._skip
        end = None if self._limit is None else start + self._limit
        return [dict(d) for d in self._docs[start:end]]


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        # ensure all docs have _id as string
        for d in self.docs:
            if "_id" not in d:
                d["_id"] = str(ObjectId())

    async def find_one(self, q):
        """
        Find and return the first document matching the query.

        Simulates MongoDB's find_one() method by scanning the in-memory
        documents list and returning the first document whose fields exactly
        match the provided query filter.

        Args:
            q (dict): MongoDB-style equality filter, e.g. {"field": value}.
                - Only exact key–value matches are supported.
                - If None or empty, the first stored document is returned.

        Returns:
            dict or None:
                - A copy of the matched document if found.
                - None if no document matches the query.

        Matching Behavior:
            - Iterates over documents in insertion order.
            - For each key–value pair in the query, the document must contain
              the key and the value must match exactly.
            - Does not support nested fields, operators, or partial comparison.

        Note:
            This is a simplified mock implementation intended for unit testing.
            It does not implement full MongoDB query semantics.
        """

        for d in self.docs:
            match = True
            for k, v in (q or {}).items():
                if d.get(k) != v:
                    match = False
                    break
            if match:
                return dict(d)
        return None

    def find(self, q=None):
        """
        Find documents matching a query in the in-memory collection.

        Simulates MongoDB's find() method by scanning all stored documents and
        returning those that match the provided filter. Supports exact-match
        queries and simple range queries using `$gte` and `$lte` operators.

        Args:
            q (dict, optional): Query filter following a subset of MongoDB syntax.
                - If None or empty, all documents are returned.
                - Supports:
                    * Exact match: {"field": value}
                    * Range queries: {"field": {"$gte": x, "$lte": y}}

        Returns:
            FakeCursor: A cursor-like object wrapping the matched documents,
            allowing iteration and chained operations used in tests.

        Query Behavior:
            - Iterates over every document in the internal list.
            - For each field in the query:
                * If the value is a dict, interprets it as a range query and
                  evaluates `$gte` and `$lte` if present.
                * Otherwise performs a direct equality match.
            - Only documents that satisfy all conditions are returned.

        Note:
            This is a mock implementation designed for testing. It does not
            support complex MongoDB operators, indexing, projections, sorting,
            or query planning. Its behavior is sufficient for unit tests that
            rely on predictable filtering logic.
        """

        q = q or {}
        filtered = []
        for d in self.docs:
            ok = True
            for k, v in q.items():
                if isinstance(v, dict):
                    # support range queries for price_including_tax
                    docv = d.get(k)
                    if docv is None:
                        ok = False
                        break
                    if "$gte" in v and docv < v["$gte"]:
                        ok = False
                        break
                    if "$lte" in v and docv > v["$lte"]:
                        ok = False
                        break
                else:
                    if d.get(k) != v:
                        ok = False
                        break
            if ok:
                filtered.append(d)
        return FakeCursor(filtered)

    async def insert_one(self, doc):
        """
        Insert a single document into the in-memory collection.

        Simulates MongoDB/Motor's insert_one behavior by assigning an auto-
        generated ObjectId (as a string) if the document does not already
        contain one, storing it in the internal document list, and returning
        an object exposing the inserted_id attribute.

        Args:
            doc (dict): The document to insert into the collection.

        Returns:
            object: A simple object with an `inserted_id` attribute containing
            the ID assigned to the newly inserted document.

        Insert Behavior:
            - Clones the input document to avoid external mutation.
            - Ensures the document has an "_id" field; creates one if missing.
            - Appends the document to the in-memory list simulating a collection.
            - Mimics Motor's insert_one by returning an object with inserted_id.

        Note:
            This is a simplified mock intended for testing. It does not validate
            document structure, enforce uniqueness, or support write concerns.
        """

        doc = dict(doc)
        if "_id" not in doc:
            doc["_id"] = str(ObjectId())
        self.docs.append(doc)

        class R:
            inserted_id = doc["_id"]

        return R()

    async def update_one(self, q, u):
        """
        Update the first document matching the query.

        Simulates MongoDB's update_one method by finding the first matching document
        and applying the $set operations to update specified fields.

        Args:
            q (dict): MongoDB-style query filter to find the document
            u (dict): Update operation document, expects {"$set": {field: value, ...}}

        Returns:
            dict: Update result with 'matched_count' key:
                - {"matched_count": 1} if a document was found and updated
                - {"matched_count": 0} if no matching document was found

        Update Behavior:
            - Finds first document matching query via find_one()
            - Applies only $set operations from update document
            - Updates fields in-place in the stored docs list
            - Does not support upsert, $inc, $push, or other operators

        Note:
            This is a simplified mock implementation for testing. Only supports
            $set operator and does not return additional MongoDB fields like
            modified_count or upserted_id.
        """
        doc = await self.find_one(q)
        if doc:
            for k, v in u.get("$set", {}).items():
                # update existing doc in stored docs
                for sd in self.docs:
                    if sd["_id"] == doc["_id"]:
                        sd[k] = v
                        break
            return {"matched_count": 1}
        return {"matched_count": 0}

    async def count_documents(self, q=None):
        """
        Count documents matching a query in the fake collection.

        Simulates MongoDB's count_documents method by iterating through documents
        and checking if they match the provided query criteria. Supports both
        exact match and range queries ($gte, $lte operators).

        Args:
            q (dict, optional): MongoDB-style query filter. Defaults to {} (all docs)

        Returns:
            int: Number of documents matching the query

        Supported Query Types:
            - Exact match: {"field": value}
            - Range queries: {"field": {"$gte": min_val, "$lte": max_val}}
            - Combined filters: All conditions must match (AND logic)

        Query Operators:
            - $gte: Greater than or equal to (inclusive minimum)
            - $lte: Less than or equal to (inclusive maximum)

        Matching Logic:
            - Document matches if ALL query conditions are satisfied
            - Missing fields fail exact matches and range checks
            - None query or empty dict {} matches all documents

        Note:
            This is a simplified implementation for testing. Does not support
            advanced MongoDB operators like $or, $in, $regex, etc.
        """
        q = q or {}
        cnt = 0
        for d in self.docs:
            ok = True
            for k, v in q.items():
                if isinstance(v, dict):
                    docv = d.get(k)
                    if docv is None:
                        ok = False
                        break
                    if "$gte" in v and docv < v["$gte"]:
                        ok = False
                        break
                    if "$lte" in v and docv > v["$lte"]:
                        ok = False
                        break
                else:
                    if d.get(k) != v:
                        ok = False
                        break
            if ok:
                cnt += 1
        return cnt

    async def to_list(self, length):
        return [dict(d) for d in self.docs[:length]]


class FakeDB:
    def __init__(self, books=None, change_log=None):
        self.books = FakeCollection(books or [])
        self.change_log = FakeCollection(change_log or [])


@pytest.fixture
def sample_books():
    """
    Sample book data fixture for testing.

    Provides a list of three mock book documents with varying attributes for
    comprehensive testing of filtering, sorting, and pagination functionality.

    Returns:
        list[dict]: Three book documents with the following characteristics:
            - book1 "Alpha": Fiction, $10, 4-star rating, 5 reviews
            - book2 "Beta": Non-Fiction, $20, 5-star rating, 10 reviews
            - book3 "Gamma": Fiction, $15, 3-star rating, 2 reviews

    Test Coverage:
        Designed to test:
        - Category filtering (2 Fiction, 1 Non-Fiction)
        - Price range filtering (prices: $10, $15, $20)
        - Rating filtering (ratings: 3, 4, 5)
        - Sorting by rating, price, and review count
        - Pagination with different page sizes

    Note:
        Books include only essential fields for API testing. Additional fields
        like description, availability, and image_url are omitted for brevity.
    """
    return [
        {
            "_id": "book1",
            "title": "Alpha",
            "category": "Fiction",
            "price_including_tax": 10.0,
            "rating": 4,
            "num_reviews": 5,
            "source_url": "http://example/book1",
        },
        {
            "_id": "book2",
            "title": "Beta",
            "category": "Non-Fiction",
            "price_including_tax": 20.0,
            "rating": 5,
            "num_reviews": 10,
            "source_url": "http://example/book2",
        },
        {
            "_id": "book3",
            "title": "Gamma",
            "category": "Fiction",
            "price_including_tax": 15.0,
            "rating": 3,
            "num_reviews": 2,
            "source_url": "http://example/book3",
        },
    ]


@pytest.fixture
def fake_db(sample_books):
    """
    Fake database fixture for testing API endpoints.

    Creates a FakeDB instance pre-populated with sample books and change log
    entries for use in isolated API tests without requiring a real MongoDB connection.

    Args:
        sample_books: pytest fixture providing a list of sample book documents

    Returns:
        FakeDB: Mock database instance with pre-loaded test data

    Contents:
        - books: Sample book collection from sample_books fixture
        - change_log: Two pre-defined change entries:
            - c1: 'new' book (book1) from 2025-01-01
            - c2: 'updated' book (book2) from 2025-01-02

    Note:
        Used in conjunction with the client fixture which patches get_db()
        to return this fake database instance during tests.
    """
    return FakeDB(
        books=sample_books,
        change_log=[
            {
                "_id": "c1",
                "book_id": "book1",
                "change_type": "new",
                "recent": "new",
                "timestamp": "2025-01-01T00:00:00Z",
            },
            {
                "_id": "c2",
                "book_id": "book2",
                "change_type": "updated",
                "recent": "new",
                "timestamp": "2025-01-02T00:00:00Z",
            },
        ],
    )


@pytest.fixture
async def client(monkeypatch, fake_db):
    """
    Async test client fixture with mocked database and authentication.

    Creates an AsyncClient for testing FastAPI endpoints with a fake database
    and overridden authentication dependency. Automatically cleans up overrides
    after test completion.

    Args:
        monkeypatch: pytest fixture for patching get_db function
        fake_db: pytest fixture providing a mock database instance

    Yields:
        AsyncClient: Configured HTTP client for making test requests to the app

    Setup:
        - Patches get_db to return fake_db instead of real MongoDB connection
        - Overrides get_api_key dependency with fake_get_api_key that accepts
          "testapikey" as valid authentication
        - Creates AsyncClient with ASGITransport for direct app communication

    Teardown:
        - Clears all dependency overrides to prevent test interference

    Authentication:
        Fake implementation accepts only "testapikey" via X-API-Key header,
        raises 401 for any other key or missing key.

    Note:
        Uses ASGITransport for efficient in-memory communication without
        actual HTTP connections. Base URL set to "http://test" for testing.
    """
    # Patch get_db to return fake_db
    monkeypatch.setattr("api.main.get_db", lambda: fake_db)

    # Override API key dependency
    async def fake_get_api_key(request: Request):
        key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
        if key != "testapikey":
            raise HTTPException(status_code=401, detail="Unauthorized")
        return key

    app.dependency_overrides[get_api_key] = fake_get_api_key

    # Use AsyncClient with FastAPI app using ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
