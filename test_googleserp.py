from src.googleserp import SearchClient


async def test_search():
    query = "site:github.com"

    client = SearchClient(
        query,
        tbs="li:1",
        max_search_result_urls_to_return=100,
        http_429_cool_off_time_in_minutes=45,
        http_429_cool_off_factor=1.5,
        # proxy="socks5h://127.0.0.1:9050",
        verbosity=5,
        verbose_output=True,  # False (only URLs) or True (rank, title, description, and URL)
    )

    urls = await client.search()

    assert isinstance(urls, list)
