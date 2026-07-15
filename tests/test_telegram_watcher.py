from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.watchers.telegram_watcher import TelegramWatcher


@pytest.fixture
def watcher():
    return TelegramWatcher(token="test:token")


@pytest.mark.asyncio
async def test_constructor_stores_token(watcher):
    assert watcher._token == "test:token"


@pytest.mark.asyncio
async def test_set_message_callback(watcher):
    async def dummy(msg):
        pass

    watcher.set_message_callback(dummy)
    assert watcher._callback is dummy


@pytest.mark.asyncio
async def test_set_monitored_groups(watcher):
    watcher.set_monitored_groups([123, 456])
    assert watcher._monitored_groups == [123, 456]


@pytest.mark.asyncio
async def test_start_initializes_and_polls(watcher):
    mock_app = MagicMock()
    mock_app.updater = MagicMock()
    mock_app.updater.start_polling = AsyncMock()

    with patch.object(
        type(watcher._app), "Application", autospec=True
    ) if False else patch(
        "backend.watchers.telegram_watcher.Application", autospec=True
    ) as mock_application_cls:
        mock_application_cls.builder.return_value.token.return_value.build.return_value = (
            mock_app
        )
        await watcher.start()

        mock_application_cls.builder.assert_called_once()
        mock_application_cls.builder.return_value.token.assert_called_once_with(
            "test:token"
        )
        assert watcher._app is mock_app


@pytest.mark.asyncio
async def test_handle_message_calls_callback(watcher):
    callback = AsyncMock()
    watcher.set_message_callback(callback)

    mock_update = MagicMock()
    mock_update.message.chat_id = 42
    mock_update.message.chat.title = "Test Group"
    mock_update.message.text = "Hello"
    mock_update.message.date = datetime(2026, 7, 14, 10, 0, 0, tzinfo=timezone.utc)
    mock_update.message.from_user.username = "testuser"

    await watcher._handle_message(mock_update, None)

    callback.assert_awaited_once_with(
        {
            "source": "telegram",
            "sender": "testuser",
            "group_name": "Test Group",
            "text": "Hello",
            "timestamp": datetime(2026, 7, 14, 10, 0, 0),
            "group_external_id": "42",
        }
    )


@pytest.mark.asyncio
async def test_handle_message_skips_if_no_text(watcher):
    callback = AsyncMock()
    watcher.set_message_callback(callback)

    mock_update = MagicMock()
    mock_update.message.text = None

    await watcher._handle_message(mock_update, None)

    callback.assert_not_called()


@pytest.mark.asyncio
async def test_handle_message_skips_if_no_message(watcher):
    callback = AsyncMock()
    watcher.set_message_callback(callback)

    mock_update = MagicMock()
    mock_update.message = None

    await watcher._handle_message(mock_update, None)

    callback.assert_not_called()


@pytest.mark.asyncio
async def test_handle_message_filters_by_monitored_groups(watcher):
    callback = AsyncMock()
    watcher.set_message_callback(callback)
    watcher.set_monitored_groups([1, 2, 3])

    mock_update = MagicMock()
    mock_update.message.chat_id = 99
    mock_update.message.text = "Hello"
    mock_update.message.date = datetime(2026, 7, 14, 10, 0, 0, tzinfo=timezone.utc)
    mock_update.message.from_user.username = "user"
    mock_update.message.chat.title = "Other Group"

    await watcher._handle_message(mock_update, None)

    callback.assert_not_called()


@pytest.mark.asyncio
async def test_handle_message_includes_monitored_group(watcher):
    callback = AsyncMock()
    watcher.set_message_callback(callback)
    watcher.set_monitored_groups([1, 42])

    mock_update = MagicMock()
    mock_update.message.chat_id = 42
    mock_update.message.chat.title = "Allowed Group"
    mock_update.message.text = "Hi"
    mock_update.message.date = datetime(2026, 7, 14, 10, 0, 0, tzinfo=timezone.utc)
    mock_update.message.from_user.username = "user"

    await watcher._handle_message(mock_update, None)

    callback.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_message_none_user(watcher):
    callback = AsyncMock()
    watcher.set_message_callback(callback)

    mock_update = MagicMock()
    mock_update.message.chat_id = 42
    mock_update.message.chat.title = "Test Group"
    mock_update.message.text = "Hello"
    mock_update.message.date = datetime(2026, 7, 14, 10, 0, 0, tzinfo=timezone.utc)
    mock_update.message.from_user = None

    await watcher._handle_message(mock_update, None)

    callback.assert_awaited_once()
    args = callback.await_args[0][0]
    assert args["sender"] is None


@pytest.mark.asyncio
async def test_stop_shuts_down(watcher):
    mock_app = MagicMock()
    mock_app.updater.stop = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.shutdown = AsyncMock()
    watcher._app = mock_app

    await watcher.stop()

    mock_app.updater.stop.assert_awaited_once()
    mock_app.stop.assert_awaited_once()
    mock_app.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_no_op_if_not_started(watcher):
    await watcher.stop()
