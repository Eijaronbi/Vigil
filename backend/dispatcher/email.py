import asyncio
import base64
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class EmailDispatcher:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str, to_email: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._to_email = to_email

    def _build_service(self):
        creds = Credentials(
            token=None,
            refresh_token=self._refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        creds.refresh(Request())
        return build("gmail", "v1", credentials=creds)

    def _build_html_table(self, messages: list[dict]) -> str:
        rows = "".join(
            f"<tr>"
            f"<td>{m.get('group_name', 'N/A')}</td>"
            f"<td>{m.get('sender', 'N/A')}</td>"
            f"<td>{m.get('text', 'N/A')}</td>"
            f"<td>{m.get('score', 'N/A')}</td>"
            f"</tr>"
            for m in messages
        )
        return f"<table border='1'><tr><th>Group</th><th>Sender</th><th>Message</th><th>Score</th></tr>{rows}</table>"

    def _send_via_gmail(self, subject: str, html_body: str) -> bool:
        service = self._build_service()
        message = MIMEText(html_body, "html")
        message["To"] = self._to_email
        message["Subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body = {"raw": raw}
        result = service.users().messages().send(userId="me", body=body).execute()
        return result.get("id") is not None

    async def send_digest(self, messages: list[dict], digest_type: str = "digest") -> bool:
        subject = "Daily Report" if digest_type == "daily" else "Message Digest"
        html_body = self._build_html_table(messages)
        return await asyncio.to_thread(self._send_via_gmail, subject, html_body)
