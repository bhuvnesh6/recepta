"""
STT provider abstraction: stt.transcribe(audio_bytes, mimetype) -> str

Primary provider is Deepgram. Voice flow (see routes/widget.py):
  browser mic -> audio -> Deepgram STT -> text -> agent -> LLM -> TTS -> audio
"""
import requests
from flask import current_app


class STTProvider:
    def transcribe(self, audio_bytes: bytes, mimetype: str = "audio/webm") -> str:
        raise NotImplementedError


class DeepgramSTTProvider(STTProvider):
    BASE_URL = "https://api.deepgram.com/v1/listen"

    def __init__(self, api_key):
        self.api_key = api_key

    def transcribe(self, audio_bytes: bytes, mimetype: str = "audio/webm") -> str:
        if not self.api_key:
            return ""
        try:
            resp = requests.post(
                self.BASE_URL,
                headers={"Authorization": f"Token {self.api_key}", "Content-Type": mimetype},
                params={"model": "nova-2", "smart_format": "true"},
                data=audio_bytes,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["results"]["channels"][0]["alternatives"][0]["transcript"]
        except Exception:
            return ""


def get_stt_provider() -> STTProvider:
    return DeepgramSTTProvider(current_app.config.get("DEEPGRAM_API_KEY", ""))
