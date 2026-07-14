import hashlib
from datetime import datetime, timezone

import httpx


class TwitterWatcher:
    def __init__(self):
        self.last_seen_ids: dict[str, set[str]] = {}

    async def poll(self, username: str) -> list[dict]:
        url = f"https://r.jina.ai/https://x.com/{username}"
        headers = {"X-Return-Format": "markdown"}
        posts = []

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=30.0)
                if resp.status_code == 404:
                    return []
                resp.raise_for_status()
                raw = resp.text
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError):
            return []

        if username not in self.last_seen_ids:
            self.last_seen_ids[username] = set()

        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("> "):
                text = line[2:].strip()
                if not text:
                    continue
                post_id = hashlib.md5(text.encode()).hexdigest()[:12]
                if post_id in self.last_seen_ids[username]:
                    continue
                self.last_seen_ids[username].add(post_id)
                posts.append({
                    "source": "twitter",
                    "sender": f"@{username}",
                    "group_name": f"Twitter/{username}",
                    "text": text,
                    "timestamp": datetime.now(timezone.utc),
                    "post_id": post_id,
                })

        return posts
