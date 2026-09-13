"""
TTS provider abstraction: tts.generate(text, voice, language) -> bytes | None

Default target provider is Sarvam; swap by implementing another class and
branching in get_tts_provider(). Callers never call an HTTP API directly.
"""
import requests
from flask import current_app


class TTSProvider:
    def generate(self, text: str, voice: str = "priya", language: str = "en") -> bytes:
        raise NotImplementedError


class SarvamTTSProvider(TTSProvider):
    BASE_URL = "https://api.sarvam.ai/text-to-speech"

    def __init__(self, api_key):
        self.api_key = api_key

    def generate(self, text: str, voice: str = "priya", language: str = "en") -> bytes:
        if not self.api_key:
            return None  # caller falls back to text-only greeting
        try:
            resp = requests.post(
                self.BASE_URL,
                headers={"API-Subscription-Key": self.api_key, "Content-Type": "application/json"},
                json={"inputs": [text], "target_language_code": language, "speaker": voice},
                timeout=20,
            )
            if resp.status_code >= 400:
                # Don't fail the whole reply just because audio couldn't be
                # generated - but DO log the real reason (e.g. an invalid
                # speaker name) instead of silently swallowing it, or this
                # becomes a "why is there no audio" mystery in production.
                print(f"[TTS] Sarvam error {resp.status_code}: {resp.text[:300]}", flush=True)
                return None
            audio_b64 = resp.json().get("audios", [None])[0]
            if not audio_b64:
                return None
            import base64
            return base64.b64decode(audio_b64)
        except Exception as e:
            print(f"[TTS] Sarvam request failed: {e}", flush=True)
            return None


def get_tts_provider() -> TTSProvider:
    provider = current_app.config.get("TTS_PROVIDER", "sarvam")
    api_key = current_app.config.get("TTS_API_KEY", "")
    if provider == "sarvam":
        return SarvamTTSProvider(api_key)
    return SarvamTTSProvider(api_key)