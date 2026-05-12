import os
from pathlib import Path


class Config:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"
    STORAGE_DIR = BASE_DIR / "storage"
    TEMPLATE_DIR = STORAGE_DIR / "templates"
    GENERATED_DIR = STORAGE_DIR / "generated"
    EXPORT_DIR = STORAGE_DIR / "exports"
    RESOURCE_DIR = STORAGE_DIR / "resources"
    DATABASE_PATH = STORAGE_DIR / "water_teaching.db"
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
