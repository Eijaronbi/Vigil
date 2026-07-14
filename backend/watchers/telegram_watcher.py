from datetime import datetime, timezone

from telegram import Update
from telegram.ext import Application, MessageHandler, filters


class TelegramWatcher:
    def __init__(self, token: str):
        self._token = token
        self._callback = None
        self._monitored_groups: list[int] | None = None
        self._app: Application | None = None

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

        msg = {
            "source": "telegram",
            "sender": update.message.from_user.username if update.message.from_user else None,
            "group_name": update.message.chat.title,
            "text": update.message.text,
            "timestamp": update.message.date.astimezone(timezone.utc).replace(tzinfo=None),
            "group_external_id": str(chat_id),
        }

        if self._callback:
            await self._callback(msg)

    async def start(self):
        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(MessageHandler(filters.TEXT, self._handle_message))
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
