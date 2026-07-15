import httpx


ICONS = {8: "\U0001f534", 5: "\U0001f7e1"}


class TelegramDispatcher:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def _icon(self, score: float) -> str:
        if score >= 8:
            return ICONS[8]
        if score >= 5:
            return ICONS[5]
        return "\U0001f535"

    async def send_alert(
        self, group_name: str, sender: str, text: str, summary: str, score: float
    ) -> bool:
        icon = self._icon(score)
        message = (
            f"{icon} *Alert: {group_name}*\n"
            f"*From:* {sender}\n"
            f"*Text:* {text}\n"
            f"*Summary:* {summary}\n"
            f"*Score:* {score:.1f}"
        )
        payload = {"chat_id": self._chat_id, "text": message, "parse_mode": "Markdown"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(self._api_url, json=payload)
        return resp.status_code == 200 and resp.json().get("ok") is True
