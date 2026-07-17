import asyncio
from datetime import datetime, timezone

import discord
from discord import Intents


class DiscordWatcher:
    def __init__(self, token: str):
        self._token = token
        self._callbacks: list = []
        self._bot: discord.Client | None = None
        self._ready = asyncio.Event()
        self._servers: list[dict] = []

    def set_callback(self, cb):
        self._callbacks.append(cb)

    async def start(self):
        intents = Intents.default()
        intents.message_content = True

        self._bot = discord.Client(intents=intents)

        @self._bot.event
        async def on_ready():
            self._servers = [
                {"id": str(g.id), "name": g.name, "member_count": g.member_count}
                for g in self._bot.guilds
            ]
            self._ready.set()

        @self._bot.event
        async def on_message(msg):
            if msg.author.bot:
                return
            if not msg.content:
                return
            payload = {
                "source": "discord",
                "sender": msg.author.name,
                "group_name": msg.guild.name if msg.guild else "DM",
                "text": msg.content,
                "timestamp": msg.created_at.replace(tzinfo=timezone.utc).replace(tzinfo=None),
                "group_external_id": str(msg.guild.id) if msg.guild else "dm",
            }
            for cb in self._callbacks:
                try:
                    cb(payload)
                except Exception:
                    pass

        asyncio.create_task(self._bot.start(self._token))
        await self._ready.wait()

    async def stop(self):
        if self._bot:
            await self._bot.close()
            self._bot = None
