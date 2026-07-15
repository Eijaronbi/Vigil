import asyncio
import io

try:
    import edge_tts

    EDGE_AVAILABLE = True
except ImportError:
    EDGE_AVAILABLE = False


class TTSEngine:
    def __init__(self, voice: str = "en-US-JennyNeural", rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    async def synthesize(self, text: str) -> bytes | None:
        if not EDGE_AVAILABLE:
            return None
        try:
            communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, pitch=self.pitch)
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            buf.seek(0)
            return buf.read()
        except Exception:
            return None

    async def synthesize_alert_summary(self, alerts: list[dict]) -> str | None:
        if not alerts:
            return None
        parts = []
        for a in alerts:
            parts.append(f"Alert from {a.get('group', 'unknown')}. {a.get('summary', a.get('text', ''))}")
        text = ". ".join(parts)
        if len(text) > 500:
            text = text[:500] + "..."
        return await self.synthesize(text)
