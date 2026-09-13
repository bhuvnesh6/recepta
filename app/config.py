import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # Session / cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # MongoDB
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/recepta")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "recepta")

    # Supabase storage
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
    SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "recepta-files")

    # AI providers
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")

    DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
    TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "sarvam")
    TTS_API_KEY = os.environ.get("TTS_API_KEY", "")

    # ---------- Real-time streaming voice pipeline (WebSocket) ----------
    # Mirrors Eva's architecture: continuous mic PCM -> Deepgram streaming
    # STT -> Groq streaming LLM -> Sarvam streaming TTS -> scheduled audio
    # playback in the browser, with barge-in and natural turn-taking pauses.
    DEEPGRAM_STREAMING_MODEL = os.environ.get("DEEPGRAM_STREAMING_MODEL", "nova-3")
    DEEPGRAM_STREAMING_LANGUAGE = os.environ.get("DEEPGRAM_STREAMING_LANGUAGE", "multi")
    VOICE_TTS_MODEL = os.environ.get("VOICE_TTS_MODEL", "bulbul:v3")
    VOICE_TTS_SPEAKER = os.environ.get("VOICE_TTS_SPEAKER", "priya")
    VOICE_TTS_PACE = float(os.environ.get("VOICE_TTS_PACE", 1.1))
    VOICE_MIC_SAMPLE_RATE = 16000     # PCM16 the browser mic sends
    VOICE_TTS_SAMPLE_RATE = 22050     # PCM16 sent back to the browser
    # Natural turn-taking: how long the pipeline waits after the visitor
    # goes quiet before replying, so it doesn't cut them off mid-thought.
    VOICE_RESPONSE_PAUSE_SECS = float(os.environ.get("VOICE_RESPONSE_PAUSE_SECS", 0.7))
    VOICE_RESPONSE_PAUSE_JITTER_SECS = float(os.environ.get("VOICE_RESPONSE_PAUSE_JITTER_SECS", 0.25))
    VOICE_SHORT_UTTERANCE_MAX_WORDS = int(os.environ.get("VOICE_SHORT_UTTERANCE_MAX_WORDS", 3))
    VOICE_SHORT_UTTERANCE_PAUSE_SECS = float(os.environ.get("VOICE_SHORT_UTTERANCE_PAUSE_SECS", 0.35))
    # Barge-in: how long after Eva starts a turn before a VAD trigger is
    # allowed to even be considered (filters line-noise at turn start), and
    # how long a VAD "candidate" interruption waits for real transcribed
    # words before it's confirmed as a genuine barge-in vs. just noise.
    VOICE_BARGE_IN_GRACE_SECS = float(os.environ.get("VOICE_BARGE_IN_GRACE_SECS", 1.0))
    VOICE_BARGE_IN_CONFIRM_MIN_CHARS = int(os.environ.get("VOICE_BARGE_IN_CONFIRM_MIN_CHARS", 2))
    VOICE_BARGE_IN_CONFIRM_TIMEOUT_SECS = float(os.environ.get("VOICE_BARGE_IN_CONFIRM_TIMEOUT_SECS", 0.6))

    # Crawler safety limits
    CRAWL_MAX_URLS = int(os.environ.get("CRAWL_MAX_URLS", 40))
    CRAWL_MAX_DEPTH = int(os.environ.get("CRAWL_MAX_DEPTH", 2))
    CRAWL_TIMEOUT_SECONDS = int(os.environ.get("CRAWL_TIMEOUT_SECONDS", 8))

    # File upload
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB
    ALLOWED_DOC_EXTENSIONS = {"pdf", "docx", "txt", "csv"}

    # App
    APP_NAME = "Recepta"
    APP_PORT = int(os.environ.get("APP_PORT", 6651))
    WIDGET_BASE_URL = os.environ.get("WIDGET_BASE_URL", f"http://localhost:6651")