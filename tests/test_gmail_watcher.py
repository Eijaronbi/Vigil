from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.watchers.gmail_watcher import GmailWatcher


@pytest.fixture
def watcher() -> GmailWatcher:
    return GmailWatcher(
        client_id="test-id",
        client_secret="test-secret",
        refresh_token="test-token",
    )


def test_constructor_stores_credentials(watcher: GmailWatcher):
    assert watcher._client_id == "test-id"
    assert watcher._client_secret == "test-secret"
    assert watcher._refresh_token == "test-token"
    assert watcher._last_check is None


@pytest.mark.asyncio
async def test_poll_returns_empty_when_no_messages(watcher: GmailWatcher):
    mock_service = MagicMock()
    mock_list = MagicMock()
    mock_list.execute = MagicMock(return_value={})

    mock_service.users.return_value.messages.return_value.list.return_value = mock_list

    with patch.object(watcher, "_build_service", return_value=mock_service):
        result = await watcher.poll()

    assert result == []
    assert watcher._last_check is not None


@pytest.mark.asyncio
async def test_poll_returns_parsed_messages(watcher: GmailWatcher):
    mock_service = MagicMock()

    details_map = {
        "msg1": {
            "id": "msg1",
            "internalDate": "1700000000000",
            "payload": {
                "headers": [
                    {"name": "From", "value": "alice@example.com"},
                    {"name": "Subject", "value": "Hello there"},
                ]
            },
        },
        "msg2": {
            "id": "msg2",
            "internalDate": "1700000100000",
            "payload": {
                "headers": [
                    {"name": "From", "value": "bob@example.com"},
                    {"name": "Subject", "value": "Team standup"},
                ]
            },
        },
    }

    mock_list = MagicMock()
    mock_list.execute = MagicMock(
        return_value={"messages": [{"id": "msg1"}, {"id": "msg2"}]}
    )

    def mock_messages_get(**kwargs):
        msg_id = kwargs["id"]
        m = MagicMock()
        m.execute = MagicMock(return_value=details_map[msg_id])
        return m

    mock_service.users.return_value.messages.return_value.list.return_value = mock_list
    mock_service.users.return_value.messages.return_value.get.side_effect = (
        mock_messages_get
    )

    with patch.object(watcher, "_build_service", return_value=mock_service):
        result = await watcher.poll()

    assert len(result) == 2
    assert result[0]["source"] == "gmail"
    assert result[0]["sender"] == "alice@example.com"
    assert result[0]["group_name"] == "inbox"
    assert result[0]["text"] == "Hello there"
    assert result[0]["timestamp"] == datetime.fromtimestamp(
        1700000000, tz=timezone.utc
    )
    assert result[1]["sender"] == "bob@example.com"
    assert result[1]["text"] == "Team standup"
    assert watcher._last_check is not None


@pytest.mark.asyncio
async def test_poll_applies_after_filter_when_last_check_exists(watcher: GmailWatcher):
    watcher._last_check = datetime(2024, 1, 1, tzinfo=timezone.utc)

    mock_service = MagicMock()
    mock_list = MagicMock()
    mock_list.execute = MagicMock(return_value={})

    mock_service.users.return_value.messages.return_value.list.return_value = mock_list

    with patch.object(watcher, "_build_service", return_value=mock_service):
        await watcher.poll()

    call_kwargs = (
        mock_service.users()
        .messages()
        .list.call_args[1]
    )
    assert "after:" in call_kwargs["q"]
