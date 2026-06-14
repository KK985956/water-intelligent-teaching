import re
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from flask import current_app


SQLITE_SCHEMA = """
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
    share_scope TEXT NOT NULL DEFAULT 'private',
    max_downloads INTEGER NOT NULL DEFAULT 0,
    expiry_time TEXT NOT NULL,
    download_count INTEGER NOT NULL DEFAULT 0,
    creator_id INTEGER,
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

CREATE TABLE IF NOT EXISTS t_exam_paper (
    exam_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    task_id TEXT NOT NULL UNIQUE,
    course_name TEXT NOT NULL,
    total_score REAL NOT NULL,
    question_count INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    content_json TEXT NOT NULL,
    preview_path TEXT NOT NULL,
    validate_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


COMMON_INDEXES = [
    ("idx_template_type_status", "t_template", "template_type, status"),
    ("idx_task_status_created", "t_generation_task", "status, created_at"),
    ("idx_validation_target", "t_validation_result", "target_id, target_type"),
    ("idx_export_target", "t_export_record", "target_id, target_type"),
    ("idx_audit_user_time", "t_audit_log", "user_id, created_at"),
]


POSTGRES_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS t_user (
        user_id SERIAL PRIMARY KEY,
        username VARCHAR(128) NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        real_name VARCHAR(128) NOT NULL,
        dept VARCHAR(128),
        role_code VARCHAR(32) NOT NULL,
        status INTEGER NOT NULL DEFAULT 1,
        created_at VARCHAR(32) NOT NULL,
        updated_at VARCHAR(32) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS t_role (
        role_code VARCHAR(32) PRIMARY KEY,
        role_name VARCHAR(64) NOT NULL,
        description TEXT,
        permission_json TEXT NOT NULL,
        status INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS t_template (
        template_id VARCHAR(64) PRIMARY KEY,
        template_name VARCHAR(255) NOT NULL,
        template_type VARCHAR(32) NOT NULL,
        file_path TEXT NOT NULL,
        version_no INTEGER NOT NULL DEFAULT 1,
        format_rule_json TEXT NOT NULL,
        placeholder_json TEXT NOT NULL,
        preview_text TEXT,
        creator_id INTEGER,
        status INTEGER NOT NULL DEFAULT 1,
        created_at VARCHAR(32) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS t_template_version (
        version_id SERIAL PRIMARY KEY,
        template_id VARCHAR(64) NOT NULL,
        version_no INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        template_name VARCHAR(255),
        format_rule_json TEXT,
        placeholder_json TEXT,
        preview_text TEXT,
        change_log TEXT,
        is_current INTEGER NOT NULL DEFAULT 1,
        created_at VARCHAR(32) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS t_generation_task (
        task_id VARCHAR(64) PRIMARY KEY,
        task_type VARCHAR(32) NOT NULL,
        user_id INTEGER NOT NULL,
        template_id VARCHAR(64) NOT NULL,
        params_json TEXT NOT NULL,
        status VARCHAR(32) NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0,
        result_path TEXT,
        result_meta_json TEXT,
        error_message TEXT,
        retry_count INTEGER NOT NULL DEFAULT 0,
        created_at VARCHAR(32) NOT NULL,
        updated_at VARCHAR(32) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS t_teaching_plan (
        plan_id VARCHAR(64) PRIMARY KEY,
        task_id VARCHAR(64) NOT NULL UNIQUE,
        course_name VARCHAR(255) NOT NULL,
        course_type VARCHAR(32) NOT NULL,
        outline_json TEXT NOT NULL,
        goals_text TEXT NOT NULL,
        key_points TEXT NOT NULL,
        validate_status VARCHAR(32) NOT NULL,
        file_path TEXT NOT NULL,
        preview_path TEXT NOT NULL,
        content_json TEXT NOT NULL,
        created_at VARCHAR(32) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS t_courseware (
        courseware_id VARCHAR(64) PRIMARY KEY,
        plan_id VARCHAR(64) NOT NULL,
        task_id VARCHAR(64) NOT NULL UNIQUE,
        slide_count INTEGER NOT NULL,
        theme_name VARCHAR(128) NOT NULL,
        file_path TEXT NOT NULL,
        preview_path TEXT NOT NULL,
        validate_status VARCHAR(32) NOT NULL,
        slides_json TEXT NOT NULL,
        content_json TEXT NOT NULL,
        created_at VARCHAR(32) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS t_resource (
        resource_id VARCHAR(64) PRIMARY KEY,
        resource_type VARCHAR(32) NOT NULL,
        resource_name VARCHAR(255) NOT NULL,
        tags TEXT,
        file_path TEXT NOT NULL,
        checksum VARCHAR(128) NOT NULL,
        uploader_id INTEGER NOT NULL,
        created_at VARCHAR(32) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS t_validation_result (
        result_id SERIAL PRIMARY KEY,
        target_id VARCHAR(64) NOT NULL,
        target_type VARCHAR(32) NOT NULL,
        issue_count INTEGER NOT NULL,
        score DOUBLE PRECISION NOT NULL,
        issues_json TEXT NOT NULL,
        status VARCHAR(32) NOT NULL,
        checked_at VARCHAR(32) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS t_export_record (
        export_id SERIAL PRIMARY KEY,
        target_id VARCHAR(64) NOT NULL,
        target_type VARCHAR(32) NOT NULL,
        format VARCHAR(32) NOT NULL,
        actual_format VARCHAR(32) NOT NULL,
        file_path TEXT NOT NULL,
        share_token VARCHAR(128) NOT NULL UNIQUE,
        share_url TEXT NOT NULL,
        share_scope VARCHAR(32) NOT NULL DEFAULT 'private',
        max_downloads INTEGER NOT NULL DEFAULT 0,
        expiry_time VARCHAR(32) NOT NULL,
        download_count INTEGER NOT NULL DEFAULT 0,
        creator_id INTEGER,
        created_at VARCHAR(32) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS t_audit_log (
        log_id SERIAL PRIMARY KEY,
        user_id INTEGER,
        action VARCHAR(64) NOT NULL,
        target_type VARCHAR(32) NOT NULL,
        target_id VARCHAR(64) NOT NULL,
        ip_addr VARCHAR(64),
        result_status VARCHAR(32) NOT NULL,
        detail TEXT,
        created_at VARCHAR(32) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS t_exam_paper (
        exam_id VARCHAR(64) PRIMARY KEY,
        plan_id VARCHAR(64) NOT NULL,
        task_id VARCHAR(64) NOT NULL UNIQUE,
        course_name VARCHAR(255) NOT NULL,
        total_score DOUBLE PRECISION NOT NULL,
        question_count INTEGER NOT NULL,
        config_json TEXT NOT NULL,
        content_json TEXT NOT NULL,
        preview_path TEXT NOT NULL,
        validate_status VARCHAR(32) NOT NULL,
        created_at VARCHAR(32) NOT NULL
    )
    """,
]


MYSQL_SCHEMA = [
    statement.replace("SERIAL PRIMARY KEY", "INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY")
    .replace("DOUBLE PRECISION", "DOUBLE")
    for statement in POSTGRES_SCHEMA
]


MIGRATION_COLUMNS = [
    (
        "t_template_version",
        "template_name",
        {"sqlite": "TEXT", "mysql": "VARCHAR(255)", "postgresql": "VARCHAR(255)"},
    ),
    ("t_template_version", "format_rule_json", {"sqlite": "TEXT", "mysql": "TEXT", "postgresql": "TEXT"}),
    ("t_template_version", "placeholder_json", {"sqlite": "TEXT", "mysql": "TEXT", "postgresql": "TEXT"}),
    ("t_template_version", "preview_text", {"sqlite": "TEXT", "mysql": "TEXT", "postgresql": "TEXT"}),
    (
        "t_export_record",
        "share_scope",
        {
            "sqlite": "TEXT NOT NULL DEFAULT 'private'",
            "mysql": "VARCHAR(32) NOT NULL DEFAULT 'private'",
            "postgresql": "VARCHAR(32) NOT NULL DEFAULT 'private'",
        },
    ),
    (
        "t_export_record",
        "max_downloads",
        {"sqlite": "INTEGER NOT NULL DEFAULT 0", "mysql": "INTEGER NOT NULL DEFAULT 0", "postgresql": "INTEGER NOT NULL DEFAULT 0"},
    ),
    ("t_export_record", "creator_id", {"sqlite": "INTEGER", "mysql": "INTEGER", "postgresql": "INTEGER"}),
]


POSTGRES_SERIAL_COLUMNS = {
    "t_user": "user_id",
    "t_template_version": "version_id",
    "t_validation_result": "result_id",
    "t_export_record": "export_id",
    "t_audit_log": "log_id",
}


def _resolve_database(config):
    database_url = str(config.get("DATABASE_URL") or "").strip()
    if database_url:
        scheme = urlparse(database_url).scheme.lower()
        if scheme in {"postgres", "postgresql", "postgresql+psycopg"}:
            config["DATABASE_DIALECT"] = "postgresql"
        elif scheme in {"mysql", "mysql+pymysql"}:
            config["DATABASE_DIALECT"] = "mysql"
        elif scheme == "sqlite":
            config["DATABASE_DIALECT"] = "sqlite"
        else:
            raise RuntimeError(f"Unsupported WATER_DATABASE_URL scheme: {scheme}")
        return database_url

    config["DATABASE_DIALECT"] = "sqlite"
    return f"sqlite:///{Path(config['DATABASE_PATH']).as_posix()}"


def _sqlite_path_from_url(database_url):
    parsed = urlparse(database_url)
    if parsed.path in {"", "/:memory:"}:
        return ":memory:"
    path = unquote(parsed.path)
    if re.match(r"^/[A-Za-z]:", path):
        path = path[1:]
    return path


def _connect_sqlite(db_path):
    connection = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def _connect_mysql(database_url, timeout):
    try:
        import pymysql
        import pymysql.cursors
    except ImportError as exc:  # pragma: no cover - depends on optional runtime dependency
        raise RuntimeError("MySQL requires the pymysql package. Run: pip install pymysql") from exc

    parsed = urlparse(database_url)
    query = parse_qs(parsed.query)
    return pymysql.connect(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=unquote(parsed.path.lstrip("/")),
        charset=query.get("charset", ["utf8mb4"])[0],
        connect_timeout=timeout,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _connect_postgresql(database_url, timeout):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depends on optional runtime dependency
        raise RuntimeError("PostgreSQL requires the psycopg package. Run: pip install psycopg[binary]") from exc

    return psycopg.connect(database_url, connect_timeout=timeout, row_factory=dict_row)


def _open_connection(config):
    database_url = _resolve_database(config)
    dialect = config["DATABASE_DIALECT"]
    timeout = int(config.get("DATABASE_POOL_TIMEOUT_SECONDS") or 30)
    if dialect == "sqlite":
        return _connect_sqlite(_sqlite_path_from_url(database_url))
    if dialect == "mysql":
        return _connect_mysql(database_url, timeout)
    return _connect_postgresql(database_url, timeout)


def _adapt_sql(sql, dialect):
    if dialect == "sqlite":
        return sql
    return sql.replace("?", "%s")


def _execute_cursor(connection, dialect, sql, params=()):
    prepared_sql = _adapt_sql(sql, dialect)
    if dialect == "sqlite":
        return connection.execute(prepared_sql, tuple(params))
    cursor = connection.cursor()
    cursor.execute(prepared_sql, tuple(params))
    return cursor


def _execute_ddl(connection, dialect, sql, params=()):
    cursor = _execute_cursor(connection, dialect, sql, params)
    try:
        cursor.close()
    except Exception:
        pass


def _close(connection):
    try:
        connection.close()
    except Exception:
        pass


def _index_exists(connection, dialect, table_name, index_name):
    if dialect == "sqlite":
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            (index_name,),
        ).fetchone()
        return row is not None
    if dialect == "mysql":
        cursor = connection.cursor()
        cursor.execute(f"SHOW INDEX FROM {table_name} WHERE Key_name = %s", (index_name,))
        row = cursor.fetchone()
        cursor.close()
        return row is not None

    cursor = connection.cursor()
    cursor.execute(
        "SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = %s",
        (index_name,),
    )
    row = cursor.fetchone()
    cursor.close()
    return row is not None


def _ensure_index(connection, dialect, index_name, table_name, columns):
    if _index_exists(connection, dialect, table_name, index_name):
        return
    _execute_ddl(connection, dialect, f"CREATE INDEX {index_name} ON {table_name}({columns})")


def _column_exists(connection, dialect, table_name, column_name):
    if dialect == "sqlite":
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return column_name in {row[1] for row in rows}
    if dialect == "mysql":
        cursor = connection.cursor()
        cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE %s", (column_name,))
        row = cursor.fetchone()
        cursor.close()
        return row is not None

    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s
        """,
        (table_name, column_name),
    )
    row = cursor.fetchone()
    cursor.close()
    return row is not None


def _ensure_column(connection, dialect, table_name, column_name, definition):
    if not _column_exists(connection, dialect, table_name, column_name):
        _execute_ddl(connection, dialect, f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _migrate(connection, dialect):
    for table_name, column_name, definitions in MIGRATION_COLUMNS:
        _ensure_column(connection, dialect, table_name, column_name, definitions[dialect])
    _ensure_index(connection, dialect, "idx_export_creator", "t_export_record", "creator_id, created_at")


def _init_sqlite(config, database_url):
    for key in ("STORAGE_DIR", "TEMPLATE_DIR", "GENERATED_DIR", "EXPORT_DIR", "RESOURCE_DIR"):
        Path(config[key]).mkdir(parents=True, exist_ok=True)

    db_path = Path(_sqlite_path_from_url(database_url))
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path = Path(f"{db_path}-journal")
    try:
        connection = _connect_sqlite(db_path)
        connection.executescript(SQLITE_SCHEMA)
        for index_name, table_name, columns in COMMON_INDEXES:
            _ensure_index(connection, "sqlite", index_name, table_name, columns)
        _migrate(connection, "sqlite")
        connection.commit()
        _close(connection)
    except sqlite3.OperationalError:
        try:
            if journal_path.exists():
                journal_path.unlink()
            connection = _connect_sqlite(db_path)
            connection.executescript(SQLITE_SCHEMA)
            for index_name, table_name, columns in COMMON_INDEXES:
                _ensure_index(connection, "sqlite", index_name, table_name, columns)
            _migrate(connection, "sqlite")
            connection.commit()
            _close(connection)
        except (PermissionError, sqlite3.OperationalError):
            fallback_path = Path(tempfile.gettempdir()) / "water_teaching_runtime.db"
            config["DATABASE_PATH"] = fallback_path
            config["DATABASE_URL"] = f"sqlite:///{fallback_path.as_posix()}"
            connection = _connect_sqlite(fallback_path)
            connection.executescript(SQLITE_SCHEMA)
            for index_name, table_name, columns in COMMON_INDEXES:
                _ensure_index(connection, "sqlite", index_name, table_name, columns)
            _migrate(connection, "sqlite")
            connection.commit()
            _close(connection)


def _init_external(config, dialect):
    for key in ("STORAGE_DIR", "TEMPLATE_DIR", "GENERATED_DIR", "EXPORT_DIR", "RESOURCE_DIR"):
        Path(config[key]).mkdir(parents=True, exist_ok=True)

    connection = _open_connection(config)
    try:
        schema = MYSQL_SCHEMA if dialect == "mysql" else POSTGRES_SCHEMA
        for statement in schema:
            _execute_ddl(connection, dialect, statement)
        for index_name, table_name, columns in COMMON_INDEXES:
            _ensure_index(connection, dialect, index_name, table_name, columns)
        _migrate(connection, dialect)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        _close(connection)


def connect():
    return _open_connection(current_app.config)


def row_to_dict(row):
    return dict(row) if row is not None else None


def init_db(config):
    database_url = _resolve_database(config)
    dialect = config["DATABASE_DIALECT"]
    if dialect == "sqlite":
        _init_sqlite(config, database_url)
        return
    _init_external(config, dialect)


def fetch_one(sql, params=()):
    connection = connect()
    dialect = current_app.config["DATABASE_DIALECT"]
    try:
        cursor = _execute_cursor(connection, dialect, sql, params)
        row = cursor.fetchone()
        return row_to_dict(row)
    finally:
        _close(connection)


def fetch_all(sql, params=()):
    connection = connect()
    dialect = current_app.config["DATABASE_DIALECT"]
    try:
        cursor = _execute_cursor(connection, dialect, sql, params)
        rows = cursor.fetchall()
        return [row_to_dict(row) for row in rows]
    finally:
        _close(connection)


def _insert_table_name(sql):
    match = re.search(r"INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, flags=re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _last_postgres_id(connection, sql):
    table_name = _insert_table_name(sql)
    column_name = POSTGRES_SERIAL_COLUMNS.get(table_name)
    if not column_name:
        return None
    cursor = connection.cursor()
    cursor.execute("SELECT currval(pg_get_serial_sequence(%s, %s)) AS id", (table_name, column_name))
    row = cursor.fetchone()
    cursor.close()
    return row["id"] if row else None


def execute(sql, params=()):
    connection = connect()
    dialect = current_app.config["DATABASE_DIALECT"]
    try:
        cursor = _execute_cursor(connection, dialect, sql, params)
        if dialect == "postgresql":
            lastrowid = _last_postgres_id(connection, sql)
        else:
            lastrowid = getattr(cursor, "lastrowid", None)
        connection.commit()
        return lastrowid
    except Exception:
        connection.rollback()
        raise
    finally:
        _close(connection)
