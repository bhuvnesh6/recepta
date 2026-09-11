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

    EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "local")

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
