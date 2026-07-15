from unittest.mock import MagicMock, patch

import pytest

from backend.dispatcher.email import EmailDispatcher
from backend.dispatcher.telegram import TelegramDispatcher


@pytest.fixture
def telegram() -> TelegramDispatcher:
    return TelegramDispatcher(bot_token="123:abc", chat_id="-100123")


@pytest.fixture
def email() -> EmailDispatcher:
    return EmailDispatcher(
        client_id="id",
        client_secret="secret",
        refresh_token="token",
        to_email="to@example.com",
    )


class TestTelegramDispatcher:
    @pytest.mark.asyncio
    async def test_send_alert_returns_true_on_success(self, telegram: TelegramDispatcher):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = mock_resp
            result = await telegram.send_alert(
                group_name="test-group",
                sender="@user",
                text="Hello",
                summary="Test summary",
                score=7.5,
            )

        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert "chat_id" in call_kwargs["json"]
        assert call_kwargs["json"]["parse_mode"] == "Markdown"

    @pytest.mark.asyncio
    async def test_send_alert_returns_false_on_failure(self, telegram: TelegramDispatcher):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"ok": False}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = mock_resp
            result = await telegram.send_alert(
                group_name="test-group",
                sender="@user",
                text="Hello",
                summary="Test summary",
                score=7.5,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_uses_red_icon_for_high_score(self, telegram: TelegramDispatcher):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = mock_resp
            await telegram.send_alert(
                group_name="g", sender="s", text="t", summary="sum", score=9.0,
            )

        text = mock_post.call_args[1]["json"]["text"]
        assert "\U0001f534" in text

    @pytest.mark.asyncio
    async def test_send_alert_uses_yellow_icon_for_medium_score(self, telegram: TelegramDispatcher):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = mock_resp
            await telegram.send_alert(
                group_name="g", sender="s", text="t", summary="sum", score=5.0,
            )

        text = mock_post.call_args[1]["json"]["text"]
        assert "\U0001f7e1" in text

    @pytest.mark.asyncio
    async def test_send_alert_uses_blue_icon_for_low_score(self, telegram: TelegramDispatcher):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = mock_resp
            await telegram.send_alert(
                group_name="g", sender="s", text="t", summary="sum", score=3.0,
            )

        text = mock_post.call_args[1]["json"]["text"]
        assert "\U0001f535" in text

    @pytest.mark.asyncio
    async def test_send_alert_uses_correct_api_url(self, telegram: TelegramDispatcher):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = mock_resp
            await telegram.send_alert(
                group_name="g", sender="s", text="t", summary="sum", score=1.0,
            )

        url = mock_post.call_args[0][0]
        assert url == "https://api.telegram.org/bot123:abc/sendMessage"


class TestEmailDispatcher:
    @pytest.mark.asyncio
    async def test_send_digest_returns_true_on_success(self, email: EmailDispatcher):
        mock_service = MagicMock()
        mock_send = MagicMock()
        mock_send.execute.return_value = {"id": "msg123"}
        mock_service.users.return_value.messages.return_value.send.return_value = mock_send

        with patch.object(email, "_send_via_gmail", return_value=True):
            result = await email.send_digest(
                messages=[{"group_name": "g", "sender": "s", "text": "t", "score": 8}],
                digest_type="digest",
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_digest_uses_daily_subject(self, email: EmailDispatcher):
        sent = {"subject": None}

        def fake_send(subject: str, html: str) -> bool:
            sent["subject"] = subject
            return True

        with patch.object(email, "_send_via_gmail", side_effect=fake_send):
            await email.send_digest(
                messages=[{"group_name": "g", "sender": "s", "text": "t", "score": 5}],
                digest_type="daily",
            )

        assert sent["subject"] == "Daily Report"

    @pytest.mark.asyncio
    async def test_send_digest_uses_digest_subject(self, email: EmailDispatcher):
        sent = {"subject": None}

        def fake_send(subject: str, html: str) -> bool:
            sent["subject"] = subject
            return True

        with patch.object(email, "_send_via_gmail", side_effect=fake_send):
            await email.send_digest(
                messages=[{"group_name": "g", "sender": "s", "text": "t", "score": 5}],
                digest_type="digest",
            )

        assert sent["subject"] == "Message Digest"

    @pytest.mark.asyncio
    async def test_send_digest_includes_html_table(self, email: EmailDispatcher):
        sent = {"html": None}

        def fake_send(subject: str, html: str) -> bool:
            sent["html"] = html
            return True

        with patch.object(email, "_send_via_gmail", side_effect=fake_send):
            await email.send_digest(
                messages=[
                    {"group_name": "group1", "sender": "alice", "text": "hi", "score": 9},
                ],
                digest_type="digest",
            )

        assert "<table" in sent["html"]
        assert "group1" in sent["html"]
        assert "alice" in sent["html"]
        assert "hi" in sent["html"]
        assert "9" in sent["html"]
