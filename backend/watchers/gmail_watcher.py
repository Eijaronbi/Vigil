import asyncio
from datetime import datetime, timezone
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class GmailWatcher:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._last_check: datetime | None = None
        self._service: Any = None

    def _build_service(self) -> Any:
        creds = Credentials(
            token=None,
            refresh_token=self._refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        creds.refresh(Request())
        return build("gmail", "v1", credentials=creds)

    async def poll(self) -> list[dict[str, Any]]:
        if self._service is None:
            self._service = await asyncio.to_thread(self._build_service)

        query = "in:inbox is:unread"
        if self._last_check is not None:
            after_ts = int(self._last_check.timestamp())
            query += f" after:{after_ts}"

        messages: list[dict[str, Any]] = []
        response = await asyncio.to_thread(
            self._service.users().messages().list,
            userId="me",
            q=query,
        )
        result = await asyncio.to_thread(response.execute)
        msg_list = result.get("messages", [])
        if not msg_list:
            self._last_check = datetime.now(timezone.utc)
            return []

        for msg in msg_list:
            detail = await asyncio.to_thread(
                self._service.users().messages().get,
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "Subject"],
            )
            data = await asyncio.to_thread(detail.execute)

            headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
            sender = headers.get("From", "unknown")
            subject = headers.get("Subject", "(no subject)")
            ts = datetime.fromtimestamp(
                int(data["internalDate"]) / 1000, tz=timezone.utc
            )

            messages.append({
                "source": "gmail",
                "sender": sender,
                "group_name": "inbox",
                "text": subject,
                "timestamp": ts,
            })

        self._last_check = datetime.now(timezone.utc)
        return messages
