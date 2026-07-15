import hashlib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.watchers.twitter_watcher import TwitterWatcher


@pytest.fixture
def watcher():
    return TwitterWatcher()


@pytest.mark.asyncio
async def test_poll_returns_posts(watcher):
    markdown = "\n> First tweet\n\n> Second tweet\n"
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = markdown

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        posts = await watcher.poll("elonmusk")

    assert len(posts) == 2
    assert posts[0]["source"] == "twitter"
    assert posts[0]["sender"] == "@elonmusk"
    assert posts[0]["group_name"] == "Twitter/elonmusk"
    assert posts[0]["text"] == "First tweet"
    expected_id = hashlib.md5("First tweet".encode()).hexdigest()[:12]
    assert posts[0]["post_id"] == expected_id
    assert posts[1]["text"] == "Second tweet"
    assert isinstance(posts[0]["timestamp"], datetime)


@pytest.mark.asyncio
async def test_poll_skips_duplicates(watcher):
    markdown = "> Duplicate\n"
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = markdown

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        posts1 = await watcher.poll("user1")
        posts2 = await watcher.poll("user1")

    assert len(posts1) == 1
    assert len(posts2) == 0


@pytest.mark.asyncio
async def test_poll_separates_usernames(watcher):
    markdown = "> Post\n"
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = markdown

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        posts_a = await watcher.poll("alice")
        posts_b = await watcher.poll("bob")

    assert len(posts_a) == 1
    assert len(posts_b) == 1
    assert posts_a[0]["group_name"] == "Twitter/alice"
    assert posts_b[0]["group_name"] == "Twitter/bob"


@pytest.mark.asyncio
async def test_poll_404_returns_empty(watcher):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        posts = await watcher.poll("nonexistent")

    assert posts == []


@pytest.mark.asyncio
async def test_poll_timeout_returns_empty(watcher):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("timeout", request=None)
        posts = await watcher.poll("user")

    assert posts == []


@pytest.mark.asyncio
async def test_poll_http_error_returns_empty(watcher):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock()
        )
        posts = await watcher.poll("user")

    assert posts == []


@pytest.mark.asyncio
async def test_poll_request_error_returns_empty(watcher):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.RequestError("error", request=MagicMock())
        posts = await watcher.poll("user")

    assert posts == []


@pytest.mark.asyncio
async def test_poll_ignores_empty_quote_lines(watcher):
    markdown = "> \n> Real post\n"
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = markdown

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        posts = await watcher.poll("user")

    assert len(posts) == 1
    assert posts[0]["text"] == "Real post"
