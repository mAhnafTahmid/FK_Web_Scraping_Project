# tests/test_crawler.py
import pytest
from crawler.crawler import Crawler


@pytest.mark.asyncio
async def test_get_all_book_links_monkeypatched(monkeypatch):
    """
    Test crawler's ability to retrieve all book links across multiple pages using mocked HTML.

    Verifies that the crawler:
    - Extracts book links from the initial page
    - Follows pagination ('next' links) to subsequent pages
    - Correctly aggregates all book links from multiple pages
    - Returns properly formatted URLs for all discovered books

    Uses monkeypatch to replace the Crawler.fetch method with a fake implementation
    that returns predefined HTML content for two pages, eliminating the need for
    actual network requests.

    Args:
        monkeypatch: pytest fixture for safely patching attributes

    Asserts:
        - Total of 3 book links are found across both pages
        - Links maintain correct ordering and URL structure
    """

    fake_pages = {
        "https://books.toscrape.com/catalogue/page-1.html": """
        <html>
            <article class="product_pod">
                <h3><a href="book_1/index.html">Book 1</a></h3>
            </article>
            <article class="product_pod">
                <h3><a href="book_2/index.html">Book 2</a></h3>
            </article>
            <li class="next"><a href="page-2.html">next</a></li>
        </html>
        """,
        "https://books.toscrape.com/catalogue/page-2.html": """
        <html>
            <article class="product_pod">
                <h3><a href="book_3/index.html">Book 3</a></h3>
            </article>
        </html>
        """,
    }

    async def fake_fetch(self, url):
        return fake_pages[url]

    monkeypatch.setattr("crawler.crawler.Crawler.fetch", fake_fetch)

    crawler = Crawler()
    links = await crawler.get_all_book_links()

    assert len(links) == 3
    assert links[0].endswith("book_1/index.html")
    assert links[1].endswith("book_2/index.html")
    assert links[2].endswith("book_3/index.html")

    await crawler.close()
