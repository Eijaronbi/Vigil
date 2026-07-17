import asyncio
import json
import re
import time

import httpx

POLL_INTERVAL = 120
JINA_BASE = "https://r.jina.ai/http"


class JinaWatcher:
    def __init__(self):
        self._profiles: list[dict] = []
        self._callbacks: list = []
        self._task: asyncio.Task | None = None
        self._running = False

    def set_callback(self, cb):
        self._callbacks.append(cb)

    def add_profile(self, platform: str, handle: str):
        for p in self._profiles:
            if p["platform"] == platform and p["handle"] == handle:
                return
        self._profiles.append({"platform": platform, "handle": handle, "last_content": "", "last_check": 0})

    def remove_profile(self, platform: str, handle: str):
        self._profiles = [p for p in self._profiles if not (p["platform"] == platform and p["handle"] == handle)]

    def get_profiles(self):
        return list(self._profiles)

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _poll_loop(self):
        while self._running:
            for profile in self._profiles:
                try:
                    await self._check_profile(profile)
                except Exception:
                    pass
                await asyncio.sleep(5)
            await asyncio.sleep(POLL_INTERVAL)

    async def _check_profile(self, profile: dict):
        platform = profile["platform"]
        handle = profile["handle"]
        url = f"{JINA_BASE}/{'x.com' if platform == 'twitter' else 'facebook.com'}/{handle}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"Accept": "text/plain"})
            if resp.status_code != 200:
                return
            content = resp.text

        if profile["last_content"] and content == profile["last_content"]:
            return
        old = profile["last_content"]
        profile["last_content"] = content
        profile["last_check"] = int(time.time())

        posts = self._parse_posts(platform, handle, content, old)
        for post in posts:
            for cb in self._callbacks:
                try:
                    cb(post)
                except Exception:
                    pass

    def _parse_posts(self, platform: str, handle: str, content: str, old_content: str) -> list[dict]:
        posts = []
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if not line or len(line) < 20:
                continue
            if platform == "twitter":
                match = re.match(r"^\d{1,2}:\d{2}\s*(AM|PM)?\s*·\s*", line)
                if not match:
                    match = re.match(r"^[A-Z][a-z]+ \d{1,2},?\s*\d{4}", line)
                if match:
                    text = line[match.end():].strip()
                    if text and (not old_content or line not in old_content):
                        posts.append({
                            "source": "twitter",
                            "sender": f"@{handle}",
                            "group_name": f"Twitter/{handle}",
                            "text": text[:500],
                            "timestamp": time.time(),
                        })
            elif platform == "facebook":
                if "shared" in line.lower() or "posted" in line.lower() or len(line) > 60:
                    if not old_content or line not in old_content:
                        posts.append({
                            "source": "facebook",
                            "sender": handle,
                            "group_name": f"Facebook/{handle}",
                            "text": line[:500],
                            "timestamp": time.time(),
                        })
        return posts[:5]
