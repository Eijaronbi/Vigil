import json

import httpx


class LLMScorer:
    def __init__(self, api_key: str, model: str = "openai/gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"

    async def score(
        self,
        text: str,
        sender: str,
        group_name: str,
        sender_rules: list | None = None,
        keyword_matches: list | None = None,
    ) -> dict:
        context = (
            f"Message from {sender} in {group_name}:\n"
            f"Text: {text}\n"
        )
        if sender_rules:
            context += f"Sender rules: {sender_rules}\n"
        if keyword_matches:
            context += f"Keyword matches: {keyword_matches}\n"

        system_prompt = (
            "You are a message importance classifier. "
            "Rate the importance of the following message on a scale of 0-10. "
            "Respond in JSON with keys: importance (integer 0-10), "
            "summary (one-sentence summary), reason (brief explanation)."
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": context},
                        ],
                    },
                    timeout=30,
                )

            if response.status_code != 200:
                return {
                    "score": 0,
                    "summary": text[:100],
                    "error": f"API returned status {response.status_code}",
                }

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            importance = int(parsed.get("importance", 0))
            importance = max(0, min(10, importance))

            return {
                "score": importance,
                "summary": str(parsed.get("summary", text[:100])),
                "reason": str(parsed.get("reason", "")),
            }

        except Exception as e:
            return {
                "score": 0,
                "summary": text[:100],
                "error": str(e),
            }
