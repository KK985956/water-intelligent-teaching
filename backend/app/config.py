import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
if load_dotenv:
    load_dotenv(ENV_FILE, override=False)
elif ENV_FILE.exists():
    for raw_line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Config:
    BASE_DIR = BASE_DIR
    DATA_DIR = BASE_DIR / "data"
    STORAGE_DIR = BASE_DIR / "storage"
    TEMPLATE_DIR = STORAGE_DIR / "templates"
    GENERATED_DIR = STORAGE_DIR / "generated"
    EXPORT_DIR = STORAGE_DIR / "exports"
    RESOURCE_DIR = STORAGE_DIR / "resources"
    DATABASE_PATH = STORAGE_DIR / "water_teaching.db"
    DATABASE_URL = os.getenv("WATER_DATABASE_URL", "")
    DATABASE_POOL_TIMEOUT_SECONDS = int(os.getenv("WATER_DATABASE_POOL_TIMEOUT_SECONDS", "30"))
    GENERATION_SERVICE_URL = os.getenv("WATER_GENERATION_SERVICE_URL", "")
    GENERATION_SERVICE_TIMEOUT_SECONDS = int(os.getenv("WATER_GENERATION_SERVICE_TIMEOUT_SECONDS", "30"))
    GENERATION_SERVICE_PORT = int(os.getenv("WATER_GENERATION_SERVICE_PORT", "5001"))
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
    AI_COURSEWARE_ENABLED = os.getenv("WATER_AI_COURSEWARE_ENABLED", "0") == "1"
    OPENAI_TEXT_MODEL = os.getenv("WATER_OPENAI_TEXT_MODEL", "gpt-4.1-mini")
    OPENAI_IMAGE_MODEL = os.getenv("WATER_OPENAI_IMAGE_MODEL", "gpt-image-1")
    OPENAI_IMAGE_ENABLED = os.getenv("WATER_OPENAI_IMAGE_ENABLED", "0") == "1"
    SECRET_KEY = os.getenv("WATER_SECRET_KEY", "water-teaching-dev-secret")
    TOKEN_TTL_SECONDS = int(os.getenv("WATER_TOKEN_TTL_SECONDS", "43200"))
    DEMO_CAPTCHA = os.getenv("WATER_DEMO_CAPTCHA", "2026")
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024
    START_WORKER = True
    START_PROGRESS_SOCKET = True
    SYNC_TASKS = False
    DEFAULT_SHARE_DAYS = 7
    MAX_TEMPLATE_PAGE_SIZE = 50
    PROGRESS_SOCKET_HOST = os.getenv("WATER_PROGRESS_SOCKET_HOST", "127.0.0.1")
    PROGRESS_SOCKET_PORT = int(os.getenv("WATER_PROGRESS_SOCKET_PORT", "8765"))
    ALLOWED_TEMPLATE_EXTENSIONS = {".doc", ".docx", ".ppt", ".pptx", ".txt", ".md"}
    ALLOWED_RESOURCE_EXTENSIONS = {
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".mp4",
        ".txt",
        ".md",
    }
