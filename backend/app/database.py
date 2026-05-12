import sqlite3
import tempfile
from pathlib import Path

from flask import current_app


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS t_user (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    real_name TEXT NOT NULL,
    dept TEXT,
    role_code TEXT NOT NULL,
    status INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_role (
    role_code TEXT PRIMARY KEY,
    role_name TEXT NOT NULL,
    description TEXT,
    permission_json TEXT NOT NULL,
    status INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS t_template (
    template_id TEXT PRIMARY KEY,
    template_name TEXT NOT NULL,
    template_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    version_no INTEGER NOT NULL DEFAULT 1,
    format_rule_json TEXT NOT NULL,
    placeholder_json TEXT NOT NULL,
    preview_text TEXT,
    creator_id INTEGER,
    status INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_template_version (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id TEXT NOT NULL,
    version_no INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    template_name TEXT,
    format_rule_json TEXT,
    placeholder_json TEXT,
    preview_text TEXT,
    change_log TEXT,
    is_current INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_generation_task (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    template_id TEXT NOT NULL,
    params_json TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    result_path TEXT,
    result_meta_json TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_teaching_plan (
    plan_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    course_name TEXT NOT NULL,
    course_type TEXT NOT NULL,
    outline_json TEXT NOT NULL,
    goals_text TEXT NOT NULL,
    key_points TEXT NOT NULL,
    validate_status TEXT NOT NULL,
    file_path TEXT NOT NULL,
    preview_path TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_courseware (
    courseware_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    task_id TEXT NOT NULL UNIQUE,
    slide_count INTEGER NOT NULL,
    theme_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    preview_path TEXT NOT NULL,
    validate_status TEXT NOT NULL,
    slides_json TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_resource (
    resource_id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    resource_name TEXT NOT NULL,
    tags TEXT,
    file_path TEXT NOT NULL,
    checksum TEXT NOT NULL,
    uploader_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_validation_result (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    issue_count INTEGER NOT NULL,
    score REAL NOT NULL,
    issues_json TEXT NOT NULL,
    status TEXT NOT NULL,
    checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_export_record (
    export_id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    format TEXT NOT NULL,
    actual_format TEXT NOT NULL,
    file_path TEXT NOT NULL,
    share_token TEXT NOT NULL UNIQUE,
    share_url TEXT NOT NULL,
    expiry_time TEXT NOT NULL,
    download_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_audit_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    ip_addr TEXT,
    result_status TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_template_type_status ON t_template(template_type, status);
CREATE INDEX IF NOT EXISTS idx_task_status_created ON t_generation_task(status, created_at);
CREATE INDEX IF NOT EXISTS idx_validation_target ON t_validation_result(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_export_target ON t_export_record(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_audit_user_time ON t_audit_log(user_id, created_at);
"""


def _connect(db_path):
    connection = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_column(connection, table_name, column_name, definition):
    existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in existing:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _migrate(connection):
    _ensure_column(connection, "t_template_version", "template_name", "TEXT")
    _ensure_column(connection, "t_template_version", "format_rule_json", "TEXT")
    _ensure_column(connection, "t_template_version", "placeholder_json", "TEXT")
    _ensure_column(connection, "t_template_version", "preview_text", "TEXT")


def connect():
    return _connect(current_app.config["DATABASE_PATH"])


def row_to_dict(row):
    return dict(row) if row is not None else None


def init_db(config):
    for key in ("STORAGE_DIR", "TEMPLATE_DIR", "GENERATED_DIR", "EXPORT_DIR", "RESOURCE_DIR"):
        Path(config[key]).mkdir(parents=True, exist_ok=True)
    db_path = Path(config["DATABASE_PATH"])
    journal_path = Path(f"{db_path}-journal")
    try:
        with _connect(db_path) as connection:
            connection.executescript(SCHEMA)
            _migrate(connection)
            connection.commit()
    except sqlite3.OperationalError:
        try:
            if journal_path.exists():
                journal_path.unlink()
            with _connect(db_path) as connection:
                connection.executescript(SCHEMA)
                _migrate(connection)
                connection.commit()
            return
        except (PermissionError, sqlite3.OperationalError):
            fallback_path = Path(tempfile.gettempdir()) / "water_teaching_runtime.db"
            config["DATABASE_PATH"] = fallback_path
            with _connect(fallback_path) as connection:
                connection.executescript(SCHEMA)
                _migrate(connection)
                connection.commit()


def fetch_one(sql, params=()):
    with connect() as connection:
        row = connection.execute(sql, params).fetchone()
    return row_to_dict(row)


def fetch_all(sql, params=()):
    with connect() as connection:
        rows = connection.execute(sql, params).fetchall()
    return [row_to_dict(row) for row in rows]


def execute(sql, params=()):
    with connect() as connection:
        cursor = connection.execute(sql, params)
        connection.commit()
        return cursor.lastrowid
