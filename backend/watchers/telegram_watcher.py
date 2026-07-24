from datetime import datetime, timezone

import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, filters


class TelegramWatcher:
    def __init__(self, token: str):
        self._token = token
        self._callback = None
        self._monitored_groups: list[int] | None = None
        self._app: Application | None = None
        self._seen_ids: set[str] = set()

    def set_message_callback(self, callback):
        self._callback = callback

    def set_monitored_groups(self, group_ids: list[int]):
        self._monitored_groups = group_ids

    async def _handle_message(self, update: Update, _context):
        if not update.message or not update.message.text:
            return

        chat_id = update.message.chat_id
        if self._monitored_groups is not None and chat_id not in self._monitored_groups:
            return

        msg = self._build_msg(update)
        if msg and self._callback:
            await self._callback(msg)

    def _build_msg(self, update: Update) -> dict | None:
        if not update.message or not update.message.text:
            return None
        msg_id = str(update.message.message_id)
        dedup_key = f"{update.message.chat_id}:{msg_id}"
        if dedup_key in self._seen_ids:
            return None
        self._seen_ids.add(dedup_key)
        chat = update.message.chat
        title = chat.title
        if not title:
            title = "DM with Bot"
        return {
            "source": "telegram",
            "sender": update.message.from_user.username if update.message.from_user else None,
            "group_name": title,
            "text": update.message.text,
            "timestamp": update.message.date.astimezone(timezone.utc).replace(tzinfo=None),
            "group_external_id": str(chat.id),
        }

    async def start(self):
        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(MessageHandler(filters.TEXT, self._handle_message))
        await self._app.initialize()
        await self._app.start()
        await self._fetch_recent_history()
        await self._app.updater.start_polling()

    async def _fetch_recent_history(self):
        tg_api = f"https://api.telegram.org/bot{self._token}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{tg_api}/getUpdates",
                    params={"limit": 100, "timeout": 5, "allowed_updates": ["message"]},
                )
                if resp.status_code != 200:
                    return
                data = resp.json()
                for raw in data.get("result", []):
                    msg_data = raw.get("message", {})
                    if not msg_data.get("text"):
                        continue
                    chat_id = msg_data.get("chat", {}).get("id")
                    title = msg_data.get("chat", {}).get("title") or "DM with Bot"
                    sender = msg_data.get("from", {}).get("username") if msg_data.get("from") else None
                    text = msg_data.get("text", "")
                    msg_id = str(msg_data.get("message_id", ""))
                    dedup_key = f"{chat_id}:{msg_id}"
                    if dedup_key in self._seen_ids:
                        continue
                    self._seen_ids.add(dedup_key)
                    if self._callback:
                        await self._callback({
                            "source": "telegram",
                            "sender": sender,
                            "group_name": title,
                            "text": text,
                            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
                            "group_external_id": str(chat_id),
                        })
        except Exception:
            pass

    async def fetch_updates(self):
        updates = []
        if self._app and self._app.updater:
            try:
                raw = await self._app.bot.get_updates(timeout=5)
                for u in raw:
                    updates.append(u.to_dict() if hasattr(u, "to_dict") else {"message": {}})
            except Exception:
                pass
        return updates

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
