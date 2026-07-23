import asyncio
import json
import re
import time

import httpx

POLL_INTERVAL = 300
JINA_BASE = "https://r.jina.ai/http"


class JinaWatcher:
    def __init__(self):
        self._profiles: list[dict] = []
        self._callbacks: list = []
        self._task: asyncio.Task | None = None
        self._running = False
        self._seen_posts: set[str] = set()

    def set_callback(self, cb):
        self._callbacks.append(cb)

    def add_profile(self, platform: str, handle: str):
        for p in self._profiles:
            if p["platform"] == platform and p["handle"] == handle:
                return
        self._profiles.append({"platform": platform, "handle": handle, "last_check": 0})

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
        posts = []

        if platform == "twitter":
            posts = await self._fetch_twitter_posts(handle)
        elif platform == "facebook":
            posts = await self._fetch_facebook_posts(handle)

        profile["last_check"] = int(time.time())

        for post in posts:
            dedup = post.get("post_id") or hash(post.get("text", ""))
            if dedup in self._seen_posts:
                continue
            self._seen_posts.add(dedup)
            for cb in self._callbacks:
                try:
                    cb(post)
                except Exception:
                    pass

    async def _fetch_twitter_posts(self, handle: str) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": f"site:x.com {handle}"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code != 200:
                    return []
                text = resp.text
                posts = []
                for match in re.finditer(
                    r'<a rel="nofollow" class="result__a" href="(https://x\.com/' + re.escape(handle) + r'/status/\d+)".*?>(.*?)</a>.*?<a class="result__snippet"[^>]*>(.*?)</a>',
                    text, re.DOTALL,
                ):
                    url = match.group(1)
                    title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                    snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
                    import html
                    title = html.unescape(title)
                    snippet = html.unescape(snippet)
                    post_id = url.split("/")[-1]
                    text_content = snippet or title
                    posts.append({
                        "source": "twitter",
                        "sender": f"@{handle}",
                        "group_name": f"Twitter/{handle}",
                        "text": text_content[:500],
                        "timestamp": time.time(),
                        "post_id": post_id,
                        "url": url,
                    })
                return posts[:10]
        except Exception:
            return []

    async def _fetch_facebook_posts(self, handle: str) -> list[dict]:
        url = f"{JINA_BASE}/facebook.com/{handle}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers={"Accept": "text/plain"})
                if resp.status_code != 200:
                    return []
                content = resp.text
                posts = []
                for line in content.split("\n"):
                    line = line.strip()
                    if not line or len(line) < 20:
                        continue
                    if "shared" in line.lower() or "posted" in line.lower() or len(line) > 60:
                        post_id = str(hash(line))[:12]
                        posts.append({
                            "source": "facebook",
                            "sender": handle,
                            "group_name": f"Facebook/{handle}",
                            "text": line[:500],
                            "timestamp": time.time(),
                            "post_id": post_id,
                        })
                return posts[:10]
        except Exception:
            return []
