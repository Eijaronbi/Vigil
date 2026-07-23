import hashlib
import re
from datetime import datetime, timezone

import httpx


class TwitterWatcher:
    def __init__(self):
        self.last_seen_ids: dict[str, set[str]] = {}

    async def poll(self, username: str) -> list[dict]:
        posts = []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": f"site:x.com {username}"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code != 200:
                    return []
                text = resp.text
                if username not in self.last_seen_ids:
                    self.last_seen_ids[username] = set()
                for match in re.finditer(
                    r'<a rel="nofollow" class="result__a" href="(https://x\.com/' + re.escape(username) + r'/status/\d+)".*?>(.*?)</a>.*?<a class="result__snippet"[^>]*>(.*?)</a>',
                    text, re.DOTALL,
                ):
                    url = match.group(1)
                    snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
                    import html as hlib
                    snippet = hlib.unescape(snippet)
                    post_id = url.split("/")[-1]
                    if post_id in self.last_seen_ids[username]:
                        continue
                    self.last_seen_ids[username].add(post_id)
                    posts.append({
                        "source": "twitter",
                        "sender": f"@{username}",
                        "group_name": f"Twitter/{username}",
                        "text": snippet[:500],
                        "timestamp": datetime.now(timezone.utc),
                        "post_id": post_id,
                        "url": url,
                    })
                return posts
        except Exception:
            return []
