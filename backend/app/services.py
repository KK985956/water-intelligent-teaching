import hashlib
import json
import shutil
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue

from flask import current_app
from werkzeug.datastructures import FileStorage

from .auth import hash_password, issue_token, verify_password
from .database import execute, fetch_all, fetch_one, init_db
from .documents import (
    build_courseware_template_context,
    build_docx,
    build_plan_template_context,
    courseware_lines,
    extract_placeholders,
    extract_template_text,
    render_courseware_html,
    render_plan_html,
    render_plan_markdown,
    teaching_plan_lines,
)
from .errors import ServiceError
from .generation_client import (
    generate_courseware,
    generate_teaching_plan,
    validate_generated_courseware,
    validate_generated_plan,
)
from .office import docx_to_pdf, fill_ppt_template, fill_word_template, html_to_pdf, pptx_to_pdf, slides_to_pptx
from .realtime import bootstrap_progress_socket, notify_user, progress_socket_settings


ROLE_SEEDS = [
    {
        "role_code": "ADMIN",
        "role_name": "管理员",
        "description": "负责模板、用户、导出与审计管理。",
        "permission_json": [
            "templates:read",
            "templates:write",
            "generation:run",
            "validation:run",
            "resources:read",
            "exports:write",
            "resources:write",
            "users:manage",
            "logs:read",
            "content:edit",
        ],
    },
    {
        "role_code": "TEACHER",
        "role_name": "教师",
        "description": "负责模板选择、资料生成、校验与导出。",
        "permission_json": [
            "templates:read",
            "templates:write",
            "generation:run",
            "validation:run",
            "resources:read",
            "exports:write",
            "resources:write",
            "content:edit",
        ],
    },
    {
        "role_code": "STUDENT",
        "role_name": "学生",
        "description": "可使用基础生成与预览功能。",
        "permission_json": [
            "templates:read",
            "generation:run",
            "resources:read",
        ],
    },
]

DEFAULT_TEMPLATE_RULES = {
    "THEORY": {
        "required_sections": ["教学目标", "教学流程", "教学总结"],
        "max_bullets_per_slide": 6,
        "body_font": "宋体",
    },
    "PRACTICE": {
        "required_sections": ["实训目标", "实训步骤", "总结考核"],
        "max_bullets_per_slide": 6,
        "body_font": "宋体",
    },
    "TRAINING": {
        "required_sections": ["培训目标", "案例分析", "总结提升"],
        "max_bullets_per_slide": 6,
        "body_font": "宋体",
    },
}

TEMPLATE_TYPE_ALIASES = {
    "THEORY": "THEORY",
    "theory": "THEORY",
    "理论": "THEORY",
    "理论课": "THEORY",
    "PRACTICE": "PRACTICE",
    "practice": "PRACTICE",
    "实践": "PRACTICE",
    "实训": "PRACTICE",
    "实训课": "PRACTICE",
    "TRAINING": "TRAINING",
    "training": "TRAINING",
    "培训": "TRAINING",
    "培训课": "TRAINING",
    "REVIEW": "REVIEW",
    "review": "REVIEW",
    "复习": "REVIEW",
}

TARGET_TYPE_ALIASES = {
    "PLAN": "PLAN",
    "plan": "PLAN",
    "TEACHING_PLAN": "PLAN",
    "COURSEWARE": "COURSEWARE",
    "courseware": "COURSEWARE",
}

RESOURCE_TYPE_ALIASES = {
    "IMAGE": "IMAGE",
    "image": "IMAGE",
    "图片": "IMAGE",
    "VIDEO": "VIDEO",
    "video": "VIDEO",
    "视频": "VIDEO",
    "CASE": "CASE",
    "case": "CASE",
    "案例": "CASE",
    "FORMULA": "FORMULA",
    "formula": "FORMULA",
    "公式": "FORMULA",
    "EXERCISE": "EXERCISE",
    "exercise": "EXERCISE",
    "习题": "EXERCISE",
}

TASK_QUEUE = Queue()
WORKER_LOCK = threading.Lock()
WORKER_STARTED = False
WORKER_APP = None


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def json_dumps(data):
    return json.dumps(data, ensure_ascii=False)


def json_loads(text, default=None):
    if not text:
        return default if default is not None else {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default if default is not None else {}


def make_id(prefix):
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def normalize_template_type(value):
    normalized = TEMPLATE_TYPE_ALIASES.get(str(value).strip(), None)
    if not normalized:
        raise ServiceError(1000, "无效的模板类型", 400)
    return normalized


def normalize_target_type(value):
    normalized = TARGET_TYPE_ALIASES.get(str(value).strip(), None)
    if not normalized:
        raise ServiceError(1000, "无效的目标类型", 400)
    return normalized


def normalize_resource_type(value):
    normalized = RESOURCE_TYPE_ALIASES.get(str(value).strip(), None)
    if not normalized:
        raise ServiceError(1000, "无效的资源类型", 400)
    return normalized


def normalize_goals(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.replace("；", ";").split(";") if item.strip()]
    return []


def normalize_user_status(value, default=1):
    if value in (None, ""):
        return default
    try:
        status = int(value)
    except (TypeError, ValueError) as exc:
        raise ServiceError(1000, "用户状态必须为 0 或 1", 400) from exc
    if status not in (0, 1):
        raise ServiceError(1000, "用户状态必须为 0 或 1", 400)
    return status


def role_permissions(role_code):
    role = fetch_one("SELECT * FROM t_role WHERE role_code = ?", (role_code,))
    if not role:
        return []
    return json_loads(role["permission_json"], [])


def ensure_role(role_code):
    role = fetch_one("SELECT * FROM t_role WHERE role_code = ?", (role_code,))
    if not role or int(role["status"]) != 1:
        raise ServiceError(1000, "角色不存在或不可用", 400)
    return role


def user_has_permission(role_code, permission):
    return permission in role_permissions(role_code)


def _can_manage_all(user_row):
    return bool(user_row and user_has_permission(user_row["role_code"], "users:manage"))


def _ensure_task_access(task_row, user_row):
    if not task_row or not user_row:
        return
    if int(task_row["user_id"]) == int(user_row["user_id"]) or _can_manage_all(user_row):
        return
    raise ServiceError(1002, "当前用户无权访问该任务", 403)


def _task_user_for_target(target_type, target_id):
    normalized_type = normalize_target_type(target_type)
    if normalized_type == "PLAN":
        return fetch_one(
            """
            SELECT gt.user_id
            FROM t_teaching_plan tp
            JOIN t_generation_task gt ON gt.task_id = tp.task_id
            WHERE tp.plan_id = ?
            """,
            (target_id,),
        )
    return fetch_one(
        """
        SELECT gt.user_id
        FROM t_courseware cw
        JOIN t_generation_task gt ON gt.task_id = cw.task_id
        WHERE cw.courseware_id = ?
        """,
        (target_id,),
    )


def _ensure_target_access(target_type, target_id, user_row):
    if not user_row:
        return
    owner = _task_user_for_target(target_type, target_id)
    if not owner:
        raise ServiceError(2003, "目标内容不存在", 404)
    if int(owner["user_id"]) == int(user_row["user_id"]) or _can_manage_all(user_row):
        return
    raise ServiceError(1002, "当前用户无权访问该内容", 403)


def get_user_by_id(user_id):
    return fetch_one("SELECT * FROM t_user WHERE user_id = ?", (user_id,))


def safe_user_view(user_row):
    return {
        "userId": user_row["user_id"],
        "username": user_row["username"],
        "realName": user_row["real_name"],
        "dept": user_row["dept"],
        "roleCode": user_row["role_code"],
        "status": user_row["status"],
    }


def _serialize_user(user_row):
    if not user_row:
        return None
    data = safe_user_view(user_row)
    data["permissions"] = role_permissions(user_row["role_code"])
    data["createdAt"] = user_row["created_at"]
    data["updatedAt"] = user_row["updated_at"]
    return data


def _serialize_role(row):
    if not row:
        return None
    return {
        "roleCode": row["role_code"],
        "roleName": row["role_name"],
        "description": row["description"] or "",
        "permissions": json_loads(row["permission_json"], []),
        "status": row["status"],
    }


def _serialize_template_version(row):
    if not row:
        return None
    return {
        "versionNo": row["version_no"],
        "filePath": row["file_path"],
        "templateName": row.get("template_name") or "",
        "formatRules": json_loads(row.get("format_rule_json"), {}),
        "placeholders": json_loads(row.get("placeholder_json"), []),
        "previewText": row.get("preview_text") or "",
        "changeLog": row["change_log"] or "",
        "isCurrent": row["is_current"],
        "createdAt": row["created_at"],
    }


def _serialize_template(row):
    if not row:
        return None
    return {
        "templateId": row["template_id"],
        "templateName": row["template_name"],
        "templateType": row["template_type"],
        "filePath": row["file_path"],
        "versionNo": row["version_no"],
        "formatRules": json_loads(row["format_rule_json"], {}),
        "placeholders": json_loads(row["placeholder_json"], []),
        "previewText": row["preview_text"] or "",
        "creatorId": row["creator_id"],
        "status": row["status"],
        "createdAt": row["created_at"],
    }


def _serialize_task(row):
    if not row:
        return None
    return {
        "taskId": row["task_id"],
        "taskType": row["task_type"],
        "userId": row["user_id"],
        "templateId": row["template_id"],
        "params": json_loads(row["params_json"], {}),
        "status": row["status"],
        "progress": row["progress"],
        "resultPath": row["result_path"],
        "result": json_loads(row["result_meta_json"], {}),
        "errorMessage": row["error_message"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _serialize_validation(row):
    if not row:
        return None
    return {
        "resultId": row["result_id"],
        "targetId": row["target_id"],
        "targetType": row["target_type"],
        "issueCount": row["issue_count"],
        "score": row["score"],
        "issues": json_loads(row["issues_json"], []),
        "status": row["status"],
        "checkedAt": row["checked_at"],
    }


def _serialize_resource(row):
    if not row:
        return None
    return {
        "resourceId": row["resource_id"],
        "resourceType": row["resource_type"],
        "resourceName": row["resource_name"],
        "tags": [item for item in (row["tags"] or "").split(",") if item],
        "filePath": row["file_path"],
        "checksum": row["checksum"],
        "uploaderId": row["uploader_id"],
        "createdAt": row["created_at"],
    }


def _serialize_audit(row):
    if not row:
        return None
    return {
        "logId": row["log_id"],
        "userId": row["user_id"],
        "username": row.get("username") or "",
        "action": row["action"],
        "targetType": row["target_type"],
        "targetId": row["target_id"],
        "ipAddr": row["ip_addr"] or "",
        "resultStatus": row["result_status"],
        "detail": row["detail"] or "",
        "createdAt": row["created_at"],
    }


def _serialize_export(row):
    if not row:
        return None
    return {
        "exportId": row["export_id"],
        "targetId": row["target_id"],
        "targetType": row["target_type"],
        "format": row["format"],
        "actualFormat": row["actual_format"],
        "shareUrl": row["share_url"],
        "shareScope": row.get("share_scope") or "private",
        "maxDownloads": row.get("max_downloads") or 0,
        "downloadCount": row["download_count"],
        "expiryTime": row["expiry_time"],
        "creatorId": row.get("creator_id"),
        "createdAt": row["created_at"],
    }


def _copy_seed_template(source_name, target_name):
    source = Path(current_app.config["DATA_DIR"]) / source_name
    target = Path(current_app.config["TEMPLATE_DIR"]) / target_name
    if not target.exists():
        shutil.copyfile(source, target)
    return target


def record_audit(user_id, action, target_type, target_id, result_status, detail="", ip_addr=""):
    execute(
        """
        INSERT INTO t_audit_log(user_id, action, target_type, target_id, ip_addr, result_status, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, action, target_type, target_id, ip_addr, result_status, detail, now_text()),
    )


def seed_defaults():
    for role in ROLE_SEEDS:
        existing = fetch_one("SELECT role_code FROM t_role WHERE role_code = ?", (role["role_code"],))
        if not existing:
            execute(
                """
                INSERT INTO t_role(role_code, role_name, description, permission_json, status)
                VALUES (?, ?, ?, ?, 1)
                """,
                (
                    role["role_code"],
                    role["role_name"],
                    role["description"],
                    json_dumps(role["permission_json"]),
                ),
            )
        else:
            execute(
                """
                UPDATE t_role
                SET role_name = ?, description = ?, permission_json = ?, status = 1
                WHERE role_code = ?
                """,
                (
                    role["role_name"],
                    role["description"],
                    json_dumps(role["permission_json"]),
                    role["role_code"],
                ),
            )

    user_rows = [
        ("admin", "admin123", "系统管理员", "水利学院", "ADMIN"),
        ("teacher", "teacher123", "示例教师", "水利工程系", "TEACHER"),
        ("student", "student123", "示例学生", "水利工程系", "STUDENT"),
    ]
    for username, password, real_name, dept, role_code in user_rows:
        existing = fetch_one("SELECT user_id FROM t_user WHERE username = ?", (username,))
        if not existing:
            execute(
                """
                INSERT INTO t_user(username, password_hash, real_name, dept, role_code, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (username, hash_password(password), real_name, dept, role_code, now_text(), now_text()),
            )

    template_count = fetch_one("SELECT COUNT(*) AS total FROM t_template")
    if int(template_count["total"]) == 0:
        teacher = fetch_one("SELECT user_id FROM t_user WHERE username = 'teacher'")
        plan_path = _copy_seed_template("sample_plan_template.md", "sample_plan_template.md")
        courseware_path = _copy_seed_template("sample_courseware_template.md", "sample_courseware_template.md")
        seed_templates = [
            (
                "TPL-2026-001",
                "理论课教学方案模板",
                "THEORY",
                str(plan_path),
                DEFAULT_TEMPLATE_RULES["THEORY"],
            ),
            (
                "TPL-2026-101",
                "标准化课件模板",
                "TRAINING",
                str(courseware_path),
                DEFAULT_TEMPLATE_RULES["TRAINING"],
            ),
        ]
        for template_id, template_name, template_type, file_path, rules in seed_templates:
            preview_text = extract_template_text(file_path)
            execute(
                """
                INSERT INTO t_template(template_id, template_name, template_type, file_path, version_no,
                    format_rule_json, placeholder_json, preview_text, creator_id, status, created_at)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, 1, ?)
                """,
                (
                    template_id,
                    template_name,
                    template_type,
                    file_path,
                    json_dumps(rules),
                    json_dumps(extract_placeholders(preview_text)),
                    preview_text,
                    teacher["user_id"],
                    now_text(),
                ),
            )
            execute(
                """
                INSERT INTO t_template_version(
                    template_id, version_no, file_path, template_name, format_rule_json, placeholder_json,
                    preview_text, change_log, is_current, created_at
                )
                VALUES (?, 1, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    template_id,
                    file_path,
                    template_name,
                    json_dumps(rules),
                    json_dumps(extract_placeholders(preview_text)),
                    preview_text,
                    "内置种子模板",
                    now_text(),
                ),
            )


def bootstrap(app):
    global WORKER_STARTED, WORKER_APP

    init_db(app.config)
    with app.app_context():
        seed_defaults()
        bootstrap_progress_socket(app)

    WORKER_APP = app
    if app.config.get("SYNC_TASKS") or not app.config.get("START_WORKER"):
        return

    with WORKER_LOCK:
        if WORKER_STARTED:
            return

        def worker_loop():
            while True:
                task_id = TASK_QUEUE.get()
                try:
                    with WORKER_APP.app_context():
                        process_task(task_id)
                finally:
                    TASK_QUEUE.task_done()

        worker = threading.Thread(target=worker_loop, name="generation-worker", daemon=True)
        worker.start()
        WORKER_STARTED = True


def authenticate_user(username, password, captcha, ip_addr=""):
    if not username or not password:
        raise ServiceError(1000, "用户名和密码不能为空", 400)
    if not captcha or str(captcha).strip() != str(current_app.config["DEMO_CAPTCHA"]).strip():
        raise ServiceError(1000, "验证码错误", 400)

    user = fetch_one("SELECT * FROM t_user WHERE username = ?", (username,))
    if not user or not verify_password(password, user["password_hash"]):
        record_audit(None, "LOGIN", "USER", username, "FAILED", "账号或密码错误", ip_addr)
        raise ServiceError(1001, "账号或密码错误", 401)

    token = issue_token(user)
    record_audit(user["user_id"], "LOGIN", "USER", str(user["user_id"]), "SUCCESS", "登录成功", ip_addr)
    return {
        "token": token,
        "userInfo": safe_user_view(user),
        "expiresIn": current_app.config["TOKEN_TTL_SECONDS"],
    }


def list_templates(template_type=None, keyword=None, page=1, size=10):
    page = max(1, int(page or 1))
    max_size = int(current_app.config["MAX_TEMPLATE_PAGE_SIZE"])
    size = max(1, min(int(size or 10), max_size))

    conditions = ["status = 1"]
    params = []
    if template_type:
        normalized_type = normalize_template_type(template_type)
        conditions.append("template_type = ?")
        params.append(normalized_type)
    if keyword:
        conditions.append("template_name LIKE ?")
        params.append(f"%{keyword.strip()}%")

    where_clause = " AND ".join(conditions)
    total_row = fetch_one(f"SELECT COUNT(*) AS total FROM t_template WHERE {where_clause}", tuple(params))
    params.extend([size, (page - 1) * size])
    rows = fetch_all(
        f"""
        SELECT * FROM t_template
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    )
    return {
        "list": [_serialize_template(row) for row in rows],
        "total": total_row["total"],
        "pageInfo": {"page": page, "size": size},
    }


def list_resources(resource_type=None, keyword=None, page=1, size=20):
    page = max(1, int(page or 1))
    size = max(1, min(int(size or 20), 100))

    conditions = ["1 = 1"]
    params = []
    if resource_type:
        normalized_type = normalize_resource_type(resource_type)
        conditions.append("resource_type = ?")
        params.append(normalized_type)
    if keyword:
        conditions.append("(resource_name LIKE ? OR tags LIKE ?)")
        params.extend([f"%{keyword.strip()}%", f"%{keyword.strip()}%"])

    where_clause = " AND ".join(conditions)
    total_row = fetch_one(f"SELECT COUNT(*) AS total FROM t_resource WHERE {where_clause}", tuple(params))
    params.extend([size, (page - 1) * size])
    rows = fetch_all(
        f"""
        SELECT * FROM t_resource
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    )
    return {
        "list": [_serialize_resource(row) for row in rows],
        "total": total_row["total"],
        "pageInfo": {"page": page, "size": size},
    }


def list_tasks(user_id, status=None, limit=20):
    limit = max(1, min(int(limit or 20), 100))
    params = [user_id]
    sql = """
        SELECT * FROM t_generation_task
        WHERE user_id = ?
    """
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = fetch_all(sql, tuple(params))
    return [_serialize_task(row) for row in rows]


def list_roles():
    rows = fetch_all(
        """
        SELECT * FROM t_role
        WHERE status = 1
        ORDER BY role_code
        """
    )
    return [_serialize_role(row) for row in rows]


def list_users(keyword=None, role_code=None, status=None, page=1, size=20):
    page = max(1, int(page or 1))
    size = max(1, min(int(size or 20), 100))
    conditions = ["1 = 1"]
    params = []

    if keyword:
        text = keyword.strip()
        conditions.append("(username LIKE ? OR real_name LIKE ? OR dept LIKE ?)")
        params.extend([f"%{text}%", f"%{text}%", f"%{text}%"])
    if role_code:
        ensure_role(role_code)
        conditions.append("role_code = ?")
        params.append(role_code)
    if status not in (None, ""):
        conditions.append("status = ?")
        params.append(normalize_user_status(status))

    where_clause = " AND ".join(conditions)
    total_row = fetch_one(f"SELECT COUNT(*) AS total FROM t_user WHERE {where_clause}", tuple(params))
    params.extend([size, (page - 1) * size])
    rows = fetch_all(
        f"""
        SELECT * FROM t_user
        WHERE {where_clause}
        ORDER BY created_at DESC, user_id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    )
    return {
        "list": [_serialize_user(row) for row in rows],
        "total": total_row["total"],
        "pageInfo": {"page": page, "size": size},
    }


def list_audit_logs(keyword=None, action=None, page=1, size=20):
    page = max(1, int(page or 1))
    size = max(1, min(int(size or 20), 100))
    conditions = ["1 = 1"]
    params = []
    if action:
        conditions.append("l.action = ?")
        params.append(str(action).strip().upper())
    if keyword:
        text = str(keyword).strip()
        conditions.append("(l.action LIKE ? OR l.target_id LIKE ? OR l.detail LIKE ? OR u.username LIKE ?)")
        params.extend([f"%{text}%", f"%{text}%", f"%{text}%", f"%{text}%"])

    where_clause = " AND ".join(conditions)
    total_row = fetch_one(
        f"""
        SELECT COUNT(*) AS total
        FROM t_audit_log l
        LEFT JOIN t_user u ON u.user_id = l.user_id
        WHERE {where_clause}
        """,
        tuple(params),
    )
    params.extend([size, (page - 1) * size])
    rows = fetch_all(
        f"""
        SELECT l.*, u.username
        FROM t_audit_log l
        LEFT JOIN t_user u ON u.user_id = l.user_id
        WHERE {where_clause}
        ORDER BY l.created_at DESC, l.log_id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    )
    return {
        "list": [_serialize_audit(row) for row in rows],
        "total": total_row["total"],
        "pageInfo": {"page": page, "size": size},
    }


def get_runtime_context(user_row):
    socket_settings = progress_socket_settings(current_app)
    return {
        "currentUser": _serialize_user(user_row),
        "permissions": role_permissions(user_row["role_code"]),
        "progressSocket": {
            "enabled": socket_settings["enabled"],
            "port": socket_settings["port"],
        },
    }


def create_user(payload, operator_id):
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()
    real_name = str(payload.get("realName", "")).strip()
    dept = str(payload.get("dept", "")).strip()
    role_code = str(payload.get("roleCode", "")).strip().upper()
    status = normalize_user_status(payload.get("status"), default=1)

    if not username:
        raise ServiceError(1000, "username 不能为空", 400)
    if not password:
        raise ServiceError(1000, "password 不能为空", 400)
    if len(password) < 6:
        raise ServiceError(1000, "password 长度不能少于 6 位", 400)
    if not real_name:
        raise ServiceError(1000, "realName 不能为空", 400)
    ensure_role(role_code)

    if fetch_one("SELECT user_id FROM t_user WHERE username = ?", (username,)):
        raise ServiceError(1000, "用户名已存在", 409)

    execute(
        """
        INSERT INTO t_user(username, password_hash, real_name, dept, role_code, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (username, hash_password(password), real_name, dept, role_code, status, now_text(), now_text()),
    )
    row = fetch_one("SELECT * FROM t_user WHERE username = ?", (username,))
    record_audit(operator_id, "USER_CREATE", "USER", str(row["user_id"]), "SUCCESS", f"创建用户 {username}")
    return _serialize_user(row)


def update_user(user_id, payload, operator_id):
    row = fetch_one("SELECT * FROM t_user WHERE user_id = ?", (user_id,))
    if not row:
        raise ServiceError(2002, "用户不存在", 404)

    real_name = str(payload.get("realName", row["real_name"])).strip() or row["real_name"]
    dept = str(payload.get("dept", row["dept"] or "")).strip()
    role_code = str(payload.get("roleCode", row["role_code"])).strip().upper() or row["role_code"]
    status = normalize_user_status(payload.get("status"), default=row["status"])
    password = str(payload.get("password", "")).strip()

    ensure_role(role_code)
    if int(row["user_id"]) == int(operator_id) and status == 0:
        raise ServiceError(1000, "不能停用当前登录账号", 400)
    if password and len(password) < 6:
        raise ServiceError(1000, "password 长度不能少于 6 位", 400)

    password_hash = row["password_hash"] if not password else hash_password(password)
    execute(
        """
        UPDATE t_user
        SET password_hash = ?, real_name = ?, dept = ?, role_code = ?, status = ?, updated_at = ?
        WHERE user_id = ?
        """,
        (password_hash, real_name, dept, role_code, status, now_text(), user_id),
    )
    updated_row = fetch_one("SELECT * FROM t_user WHERE user_id = ?", (user_id,))
    detail = "更新用户资料"
    if password:
        detail = "更新用户资料并重置密码"
    record_audit(operator_id, "USER_UPDATE", "USER", str(user_id), "SUCCESS", detail)
    return _serialize_user(updated_row)


def get_template_detail(template_id):
    row = fetch_one("SELECT * FROM t_template WHERE template_id = ?", (template_id,))
    if not row:
        raise ServiceError(2002, "模板不存在或已下线", 404)
    versions = fetch_all(
        """
        SELECT version_no, file_path, template_name, format_rule_json, placeholder_json, preview_text,
            change_log, is_current, created_at
        FROM t_template_version
        WHERE template_id = ?
        ORDER BY version_no DESC
        """,
        (template_id,),
    )
    detail = _serialize_template(row)
    detail["versionHistory"] = [_serialize_template_version(version) for version in versions]
    detail["previewUrl"] = f"/api/v1/templates/{template_id}"
    return detail


def _parse_rules_json(raw_rules, template_type, fallback=None):
    if raw_rules in (None, ""):
        if fallback is not None:
            return fallback
        return DEFAULT_TEMPLATE_RULES[template_type]
    if isinstance(raw_rules, dict):
        return raw_rules
    try:
        parsed = json.loads(raw_rules)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    raise ServiceError(1000, "rulesJson 不是合法 JSON 对象", 400)


def _store_template_version(
    template_id,
    version_no,
    file_path,
    template_name,
    rules,
    placeholders,
    preview_text,
    change_log,
    created_at,
    is_current=1,
):
    execute(
        """
        INSERT INTO t_template_version(
            template_id, version_no, file_path, template_name, format_rule_json, placeholder_json,
            preview_text, change_log, is_current, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            template_id,
            version_no,
            str(file_path),
            template_name,
            json_dumps(rules),
            json_dumps(placeholders),
            preview_text,
            change_log,
            is_current,
            created_at,
        ),
    )


def create_template(upload_file, template_type, template_name, rules_json, user_id):
    if not isinstance(upload_file, FileStorage) or not upload_file.filename:
        raise ServiceError(1000, "请上传模板文件", 400)

    normalized_type = normalize_template_type(template_type)
    suffix = Path(upload_file.filename).suffix.lower()
    if suffix not in current_app.config["ALLOWED_TEMPLATE_EXTENSIONS"]:
        raise ServiceError(1000, "不支持的模板文件格式", 415)

    template_id = make_id("TPL")
    destination = Path(current_app.config["TEMPLATE_DIR"]) / f"{template_id}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    upload_file.save(destination)

    preview_text = extract_template_text(destination)
    placeholders = extract_placeholders(preview_text)
    rules = _parse_rules_json(rules_json, normalized_type)
    created_at = now_text()
    execute(
        """
        INSERT INTO t_template(template_id, template_name, template_type, file_path, version_no,
            format_rule_json, placeholder_json, preview_text, creator_id, status, created_at)
        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, 1, ?)
        """,
        (
            template_id,
            template_name.strip() if template_name else upload_file.filename,
            normalized_type,
            str(destination),
            json_dumps(rules),
            json_dumps(placeholders),
            preview_text,
            user_id,
            created_at,
        ),
    )
    _store_template_version(
        template_id,
        1,
        destination,
        template_name.strip() if template_name else upload_file.filename,
        rules,
        placeholders,
        preview_text,
        "模板上传",
        created_at,
    )
    record_audit(user_id, "TEMPLATE_UPLOAD", "TEMPLATE", template_id, "SUCCESS", "上传模板")
    return get_template_detail(template_id)


def upload_template_version(template_id, upload_file, change_log, rules_json, user_id, template_name=""):
    template_row = fetch_one("SELECT * FROM t_template WHERE template_id = ?", (template_id,))
    if not template_row:
        raise ServiceError(2002, "模板不存在或已下线", 404)
    if not isinstance(upload_file, FileStorage) or not upload_file.filename:
        raise ServiceError(1000, "请上传模板文件", 400)

    suffix = Path(upload_file.filename).suffix.lower()
    if suffix not in current_app.config["ALLOWED_TEMPLATE_EXTENSIONS"]:
        raise ServiceError(1000, "不支持的模板文件格式", 415)

    next_version = int(template_row["version_no"]) + 1
    destination = Path(current_app.config["TEMPLATE_DIR"]) / f"{template_id}_v{next_version}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    upload_file.save(destination)

    preview_text = extract_template_text(destination)
    placeholders = extract_placeholders(preview_text)
    current_rules = json_loads(template_row["format_rule_json"], {})
    rules = _parse_rules_json(rules_json, template_row["template_type"], current_rules)
    updated_name = template_name.strip() if str(template_name or "").strip() else template_row["template_name"]
    created_at = now_text()

    execute("UPDATE t_template_version SET is_current = 0 WHERE template_id = ?", (template_id,))
    _store_template_version(
        template_id,
        next_version,
        destination,
        updated_name,
        rules,
        placeholders,
        preview_text,
        str(change_log or "模板升级"),
        created_at,
    )
    execute(
        """
        UPDATE t_template
        SET template_name = ?, file_path = ?, version_no = ?, format_rule_json = ?, placeholder_json = ?,
            preview_text = ?, status = 1
        WHERE template_id = ?
        """,
        (
            updated_name,
            str(destination),
            next_version,
            json_dumps(rules),
            json_dumps(placeholders),
            preview_text,
            template_id,
        ),
    )
    record_audit(user_id, "TEMPLATE_VERSION_UPLOAD", "TEMPLATE", template_id, "SUCCESS", f"上传模板版本 v{next_version}")
    return get_template_detail(template_id)


def rollback_template_version(template_id, version_no, user_id):
    template_row = fetch_one("SELECT * FROM t_template WHERE template_id = ?", (template_id,))
    if not template_row:
        raise ServiceError(2002, "模板不存在或已下线", 404)
    version_row = fetch_one(
        """
        SELECT * FROM t_template_version
        WHERE template_id = ? AND version_no = ?
        """,
        (template_id, int(version_no)),
    )
    if not version_row:
        raise ServiceError(2002, "指定模板版本不存在", 404)

    preview_text = version_row.get("preview_text") or extract_template_text(version_row["file_path"])
    placeholders = json_loads(version_row.get("placeholder_json"), None) or extract_placeholders(preview_text)
    rules = json_loads(version_row.get("format_rule_json"), None) or json_loads(template_row["format_rule_json"], {})
    rollback_name = version_row.get("template_name") or template_row["template_name"]

    execute("UPDATE t_template_version SET is_current = 0 WHERE template_id = ?", (template_id,))
    execute(
        "UPDATE t_template_version SET is_current = 1 WHERE template_id = ? AND version_no = ?",
        (template_id, int(version_no)),
    )
    execute(
        """
        UPDATE t_template
        SET template_name = ?, file_path = ?, version_no = ?, format_rule_json = ?, placeholder_json = ?,
            preview_text = ?, status = 1
        WHERE template_id = ?
        """,
        (
            rollback_name,
            version_row["file_path"],
            int(version_no),
            json_dumps(rules),
            json_dumps(placeholders),
            preview_text,
            template_id,
        ),
    )
    record_audit(user_id, "TEMPLATE_ROLLBACK", "TEMPLATE", template_id, "SUCCESS", f"回滚至模板版本 v{version_no}")
    return get_template_detail(template_id)


def _dispatch_task(task_id):
    if current_app.config.get("SYNC_TASKS"):
        process_task(task_id)
    else:
        TASK_QUEUE.put(task_id)


def _validate_plan_payload(payload):
    if not payload.get("templateId"):
        raise ServiceError(1000, "templateId 不能为空", 400)
    if not payload.get("courseName"):
        raise ServiceError(1000, "courseName 不能为空", 400)
    if not payload.get("audience"):
        raise ServiceError(1000, "audience 不能为空", 400)
    try:
        hours = int(payload.get("hours"))
    except (TypeError, ValueError) as exc:
        raise ServiceError(1000, "hours 必须为整数", 400) from exc
    if hours <= 0:
        raise ServiceError(1000, "hours 必须大于 0", 400)
    template = fetch_one("SELECT * FROM t_template WHERE template_id = ?", (payload["templateId"],))
    if not template:
        raise ServiceError(2002, "模板不存在或已下线", 404)
    return template


def create_plan_task(user_id, payload):
    template = _validate_plan_payload(payload)
    params = {
        "templateId": template["template_id"],
        "courseName": payload["courseName"].strip(),
        "hours": int(payload["hours"]),
        "audience": payload["audience"].strip(),
        "goals": normalize_goals(payload.get("goals")),
        "focusPoints": normalize_goals(payload.get("focusPoints")),
        "generatedAt": now_text(),
    }
    task_id = make_id("TASK")
    execute(
        """
        INSERT INTO t_generation_task(task_id, task_type, user_id, template_id, params_json, status, progress,
            result_path, result_meta_json, error_message, retry_count, created_at, updated_at)
        VALUES (?, 'PLAN', ?, ?, ?, 'CREATED', 0, '', '{}', '', 0, ?, ?)
        """,
        (task_id, user_id, template["template_id"], json_dumps(params), now_text(), now_text()),
    )
    record_audit(user_id, "TASK_CREATE", "PLAN", task_id, "SUCCESS", "创建教学方案生成任务")
    _dispatch_task(task_id)
    return get_task(task_id)


def _validate_courseware_payload(payload):
    if not payload.get("planId"):
        raise ServiceError(1000, "planId 不能为空", 400)
    if not payload.get("coursewareTemplateId"):
        raise ServiceError(1000, "coursewareTemplateId 不能为空", 400)
    plan = fetch_one("SELECT * FROM t_teaching_plan WHERE plan_id = ?", (payload["planId"],))
    if not plan:
        raise ServiceError(2003, "教学方案不存在，无法生成课件", 404)
    template = fetch_one("SELECT * FROM t_template WHERE template_id = ?", (payload["coursewareTemplateId"],))
    if not template:
        raise ServiceError(2002, "模板不存在或已下线", 404)
    return plan, template


def create_courseware_task(user_id, payload):
    plan, template = _validate_courseware_payload(payload)
    user_row = get_user_by_id(user_id)
    _ensure_target_access("PLAN", plan["plan_id"], user_row)
    resource_ids = payload.get("resources", []) if isinstance(payload.get("resources", []), list) else []
    params = {
        "planId": plan["plan_id"],
        "coursewareTemplateId": template["template_id"],
        "resources": resource_ids,
        "generatedAt": now_text(),
    }
    task_id = make_id("TASK")
    execute(
        """
        INSERT INTO t_generation_task(task_id, task_type, user_id, template_id, params_json, status, progress,
            result_path, result_meta_json, error_message, retry_count, created_at, updated_at)
        VALUES (?, 'COURSEWARE', ?, ?, ?, 'CREATED', 0, '', '{}', '', 0, ?, ?)
        """,
        (task_id, user_id, template["template_id"], json_dumps(params), now_text(), now_text()),
    )
    record_audit(user_id, "TASK_CREATE", "COURSEWARE", task_id, "SUCCESS", "创建教学课件生成任务")
    _dispatch_task(task_id)
    return get_task(task_id)


def get_task(task_id, user_row=None):
    task = fetch_one("SELECT * FROM t_generation_task WHERE task_id = ?", (task_id,))
    if not task:
        raise ServiceError(2002, "任务不存在", 404)
    _ensure_task_access(task, user_row)
    return _serialize_task(task)


def _is_task_canceled(task_id):
    row = fetch_one("SELECT status FROM t_generation_task WHERE task_id = ?", (task_id,))
    return bool(row and row["status"] == "CANCELED")


def cancel_task(task_id, user_row):
    task = fetch_one("SELECT * FROM t_generation_task WHERE task_id = ?", (task_id,))
    if not task:
        raise ServiceError(2002, "任务不存在", 404)
    _ensure_task_access(task, user_row)
    if task["status"] in {"SUCCESS", "FAILED", "CANCELED"}:
        return _serialize_task(task)
    _update_task(task_id, "CANCELED", 100, error_message="用户主动取消任务")
    record_audit(user_row["user_id"], "TASK_CANCEL", task["task_type"], task_id, "SUCCESS", "取消异步生成任务")
    return get_task(task_id, user_row)


def retry_task(task_id, user_row):
    task = fetch_one("SELECT * FROM t_generation_task WHERE task_id = ?", (task_id,))
    if not task:
        raise ServiceError(2002, "任务不存在", 404)
    _ensure_task_access(task, user_row)
    if task["status"] not in {"FAILED", "CANCELED"}:
        raise ServiceError(1000, "只有失败或已取消的任务可以重试", 400)
    retry_count = int(task["retry_count"] or 0) + 1
    if retry_count > 3:
        raise ServiceError(5000, "任务重试次数已超过上限，请人工检查模板或参数", 400)
    execute(
        """
        UPDATE t_generation_task
        SET status = 'CREATED', progress = 0, result_path = '', result_meta_json = '{}',
            error_message = '', retry_count = ?, updated_at = ?
        WHERE task_id = ?
        """,
        (retry_count, now_text(), task_id),
    )
    record_audit(user_row["user_id"], "TASK_RETRY", task["task_type"], task_id, "SUCCESS", f"第 {retry_count} 次重试任务")
    _dispatch_task(task_id)
    return get_task(task_id, user_row)


def _update_task(task_id, status, progress, result_path=None, result_meta=None, error_message=None):
    if status != "CANCELED" and _is_task_canceled(task_id):
        return
    execute(
        """
        UPDATE t_generation_task
        SET status = ?, progress = ?, result_path = ?, result_meta_json = ?, error_message = ?, updated_at = ?
        WHERE task_id = ?
        """,
        (
            status,
            progress,
            result_path or "",
            json_dumps(result_meta or {}),
            error_message or "",
            now_text(),
            task_id,
        ),
    )
    task_row = fetch_one("SELECT * FROM t_generation_task WHERE task_id = ?", (task_id,))
    if task_row:
        notify_user(
            task_row["user_id"],
            {
                "type": "task.updated",
                "task": _serialize_task(task_row),
                "eventAt": now_text(),
            },
        )


def _create_validation_record(target_id, target_type, validation):
    execute(
        """
        INSERT INTO t_validation_result(target_id, target_type, issue_count, score, issues_json, status, checked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            target_id,
            target_type,
            len(validation["issues"]),
            validation["score"],
            json_dumps(validation["issues"]),
            validation["status"],
            now_text(),
        ),
    )


def _ensure_result_dir(task_id):
    result_dir = Path(current_app.config["GENERATED_DIR"]) / task_id
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_dir


def _write_text(path, content):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


def _format_replacement_value(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "\n".join([str(item) for item in value if str(item).strip()])
    if isinstance(value, dict):
        return json_dumps(value)
    return str(value)


def _office_placeholder_map(context):
    replacements = {}
    for key, value in context.items():
        normalized_key = str(key).strip()
        if not normalized_key or normalized_key.startswith("_"):
            continue
        replacement_value = _format_replacement_value(value)
        replacements[f"{{{{{normalized_key}}}}}"] = replacement_value
        replacements[f"{{{{ {normalized_key} }}}}"] = replacement_value
    return replacements


def _build_plan_docx(template_meta, plan, result_dir):
    docx_path = result_dir / "plan.docx"
    template_path = Path(template_meta["filePath"])
    warning = ""

    if template_path.suffix.lower() in {".doc", ".docx"}:
        try:
            fill_word_template(template_path, docx_path, _office_placeholder_map(build_plan_template_context(plan)))
            return docx_path, warning
        except Exception as exc:
            warning = str(exc)

    build_docx(docx_path, teaching_plan_lines(plan), f"{plan['course_name']}教学方案")
    return docx_path, warning


def _build_courseware_presentation(template_meta, courseware, result_dir):
    pptx_path = result_dir / "courseware.pptx"
    template_path = Path(template_meta["filePath"])
    warning = ""

    if template_path.suffix.lower() in {".ppt", ".pptx"}:
        try:
            fill_ppt_template(template_path, pptx_path, _office_placeholder_map(build_courseware_template_context(courseware)))
            return pptx_path, warning
        except Exception as exc:
            warning = str(exc)

    try:
        slides_to_pptx(courseware["slides"], pptx_path)
        return pptx_path, warning
    except Exception as exc:
        if warning:
            warning = f"{warning}；{exc}"
        else:
            warning = str(exc)
        return None, warning


def _build_plan_result(task):
    template_row = fetch_one("SELECT * FROM t_template WHERE template_id = ?", (task["template_id"],))
    if not template_row:
        raise ServiceError(2002, "模板不存在或已下线", 404)

    template_meta = _serialize_template(template_row)
    params = json_loads(task["params_json"], {})
    plan = generate_teaching_plan(params, template_meta)
    template_suffix = Path(template_meta["filePath"]).suffix.lower()
    template_body = extract_template_text(template_meta["filePath"]) if template_suffix in {".md", ".txt"} else ""
    markdown_text = render_plan_markdown(plan, template_body)
    html_text = render_plan_html(plan)
    result_dir = _ensure_result_dir(task["task_id"])
    markdown_path = result_dir / "plan.md"
    preview_path = result_dir / "plan_preview.html"
    json_path = result_dir / "plan.json"
    _write_text(markdown_path, markdown_text)
    _write_text(preview_path, html_text)
    _write_text(json_path, json_dumps(plan))
    docx_path, template_warning = _build_plan_docx(template_meta, plan, result_dir)

    validation = validate_generated_plan(plan, template_meta["formatRules"])
    validation_status = validation["status"]
    plan_id = make_id("PLAN")
    execute(
        """
        INSERT INTO t_teaching_plan(plan_id, task_id, course_name, course_type, outline_json, goals_text,
            key_points, validate_status, file_path, preview_path, content_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            plan_id,
            task["task_id"],
            plan["course_name"],
            plan["course_type"],
            json_dumps(plan["outline"]),
            "\n".join(plan["goals"]),
            "；".join(plan["focus_points"]),
            validation_status,
            str(docx_path),
            str(preview_path),
            json_dumps(plan),
            now_text(),
        ),
    )
    _create_validation_record(plan_id, "PLAN", validation)
    result_meta = {
        "targetType": "PLAN",
        "targetId": plan_id,
        "previewUrl": f"/api/v1/previews/plan/{plan_id}",
        "downloadHint": str(docx_path),
        "score": validation["score"],
        "validationStatus": validation_status,
        "files": {
            "markdown": str(markdown_path),
            "html": str(preview_path),
            "json": str(json_path),
            "docx": str(docx_path),
        },
        "templateMode": "office-template" if template_suffix in {".doc", ".docx"} else "structured-docx",
    }
    if template_warning:
        result_meta["warnings"] = [template_warning]
    return result_meta, str(docx_path)


def _build_courseware_result(task):
    params = json_loads(task["params_json"], {})
    plan_row = fetch_one("SELECT * FROM t_teaching_plan WHERE plan_id = ?", (params["planId"],))
    if not plan_row:
        raise ServiceError(2003, "教学方案不存在，无法生成课件", 404)
    template_row = fetch_one("SELECT * FROM t_template WHERE template_id = ?", (task["template_id"],))
    if not template_row:
        raise ServiceError(2002, "模板不存在或已下线", 404)

    resource_ids = params.get("resources", [])
    resources = []
    for resource_id in resource_ids:
        resource_row = fetch_one("SELECT * FROM t_resource WHERE resource_id = ?", (resource_id,))
        if resource_row:
            resources.append(_serialize_resource(resource_row))

    plan = json_loads(plan_row["content_json"], {})
    template_meta = _serialize_template(template_row)
    courseware = generate_courseware(plan, template_meta, resources)

    result_dir = _ensure_result_dir(task["task_id"])
    preview_path = result_dir / "courseware_preview.html"
    json_path = result_dir / "courseware.json"
    outline_path = result_dir / "courseware_outline.txt"
    _write_text(preview_path, render_courseware_html(courseware))
    _write_text(json_path, json_dumps(courseware))
    _write_text(outline_path, "\n".join(courseware_lines(courseware)))
    presentation_path, presentation_warning = _build_courseware_presentation(template_meta, courseware, result_dir)

    validation = validate_generated_courseware(courseware, template_meta["formatRules"])
    courseware_id = make_id("CW")
    execute(
        """
        INSERT INTO t_courseware(courseware_id, plan_id, task_id, slide_count, theme_name, file_path,
            preview_path, validate_status, slides_json, content_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            courseware_id,
            plan_row["plan_id"],
            task["task_id"],
            courseware["slide_count"],
            courseware["theme_name"],
            str(presentation_path or json_path),
            str(preview_path),
            validation["status"],
            json_dumps(courseware["slides"]),
            json_dumps(courseware),
            now_text(),
        ),
    )
    _create_validation_record(courseware_id, "COURSEWARE", validation)
    result_meta = {
        "targetType": "COURSEWARE",
        "targetId": courseware_id,
        "previewUrl": f"/api/v1/previews/courseware/{courseware_id}",
        "downloadHint": str(json_path),
        "slideCount": courseware["slide_count"],
        "score": validation["score"],
        "validationStatus": validation["status"],
        "files": {
            "html": str(preview_path),
            "json": str(json_path),
            "outline": str(outline_path),
            "pptx": str(presentation_path) if presentation_path else "",
        },
        "templateMode": "office-template" if Path(template_meta["filePath"]).suffix.lower() in {".ppt", ".pptx"} else "generated-deck",
    }
    if presentation_warning:
        result_meta["warnings"] = [presentation_warning]
    return result_meta, str(presentation_path or json_path)


def _latest_validation(target_id, target_type):
    row = fetch_one(
        """
        SELECT * FROM t_validation_result
        WHERE target_id = ? AND target_type = ?
        ORDER BY result_id DESC
        LIMIT 1
        """,
        (target_id, target_type),
    )
    return _serialize_validation(row)


def get_generated_content(target_id, target_type, user_row):
    normalized_type = normalize_target_type(target_type)
    _ensure_target_access(normalized_type, target_id, user_row)
    if normalized_type == "PLAN":
        row = fetch_one("SELECT * FROM t_teaching_plan WHERE plan_id = ?", (target_id,))
        if not row:
            raise ServiceError(2003, "教学方案不存在", 404)
        content = json_loads(row["content_json"], {})
        return {
            "targetId": target_id,
            "targetType": normalized_type,
            "content": content,
            "previewUrl": f"/api/v1/previews/plan/{target_id}",
            "validation": _latest_validation(target_id, normalized_type),
            "updatedFrom": row["file_path"],
        }

    row = fetch_one("SELECT * FROM t_courseware WHERE courseware_id = ?", (target_id,))
    if not row:
        raise ServiceError(2003, "教学课件不存在", 404)
    content = json_loads(row["content_json"], {})
    return {
        "targetId": target_id,
        "targetType": normalized_type,
        "content": content,
        "previewUrl": f"/api/v1/previews/courseware/{target_id}",
        "validation": _latest_validation(target_id, normalized_type),
        "updatedFrom": row["file_path"],
    }


def _load_task_template(task_id):
    task = fetch_one("SELECT * FROM t_generation_task WHERE task_id = ?", (task_id,))
    if not task:
        raise ServiceError(2002, "任务不存在", 404)
    template_row = fetch_one("SELECT * FROM t_template WHERE template_id = ?", (task["template_id"],))
    if not template_row:
        raise ServiceError(2002, "模板不存在或已下线", 404)
    return task, _serialize_template(template_row)


def _refresh_task_result(task_id, result_path, result_meta):
    task_row = fetch_one("SELECT * FROM t_generation_task WHERE task_id = ?", (task_id,))
    if not task_row:
        return
    current_meta = json_loads(task_row["result_meta_json"], {})
    current_meta.update(result_meta)
    execute(
        """
        UPDATE t_generation_task
        SET result_path = ?, result_meta_json = ?, updated_at = ?
        WHERE task_id = ?
        """,
        (str(result_path), json_dumps(current_meta), now_text(), task_id),
    )
    updated_task = fetch_one("SELECT * FROM t_generation_task WHERE task_id = ?", (task_id,))
    if updated_task:
        notify_user(
            updated_task["user_id"],
            {
                "type": "task.updated",
                "task": _serialize_task(updated_task),
                "eventAt": now_text(),
            },
        )


def _require_content_object(payload):
    content = payload.get("content", payload)
    if not isinstance(content, dict):
        raise ServiceError(1000, "content 必须是 JSON 对象", 400)
    return content


def _normalize_text_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        normalized = value.replace("；", ";").replace("\r", "\n").replace("\n", ";")
        return [item.strip() for item in normalized.split(";") if item.strip()]
    return []


def update_generated_content(target_id, target_type, payload, user_row):
    normalized_type = normalize_target_type(target_type)
    _ensure_target_access(normalized_type, target_id, user_row)
    if normalized_type == "PLAN":
        return _update_plan_content(target_id, payload, user_row)
    return _update_courseware_content(target_id, payload, user_row)


def _update_plan_content(plan_id, payload, user_row):
    row = fetch_one("SELECT * FROM t_teaching_plan WHERE plan_id = ?", (plan_id,))
    if not row:
        raise ServiceError(2003, "教学方案不存在", 404)
    incoming = _require_content_object(payload)
    plan = json_loads(row["content_json"], {})
    plan.update(incoming)

    for key in ("goals", "focus_points", "difficult_points", "cases", "exercises", "homework", "resources", "formulas"):
        plan[key] = _normalize_text_list(plan.get(key))
    if not plan.get("course_name"):
        raise ServiceError(1000, "course_name 不能为空", 400)
    if not plan.get("audience"):
        raise ServiceError(1000, "audience 不能为空", 400)
    try:
        plan["hours"] = int(plan.get("hours") or 1)
    except (TypeError, ValueError) as exc:
        raise ServiceError(1000, "hours 必须为整数", 400) from exc
    plan["outline"] = plan.get("outline") if isinstance(plan.get("outline"), list) else []
    for index, item in enumerate(plan["outline"]):
        if not isinstance(item, dict):
            raise ServiceError(1000, f"outline[{index}] 必须是对象", 400)
        item["title"] = str(item.get("title", "")).strip()
        item["duration"] = str(item.get("duration", "")).strip()
        item["content"] = str(item.get("content", "")).strip()
        item["method"] = str(item.get("method", "")).strip()
        item["knowledge_points"] = _normalize_text_list(item.get("knowledge_points"))

    task, template_meta = _load_task_template(row["task_id"])
    template_suffix = Path(template_meta["filePath"]).suffix.lower()
    template_body = extract_template_text(template_meta["filePath"]) if template_suffix in {".md", ".txt"} else ""
    result_dir = _ensure_result_dir(task["task_id"])
    markdown_path = result_dir / "plan.md"
    preview_path = result_dir / "plan_preview.html"
    json_path = result_dir / "plan.json"
    _write_text(markdown_path, render_plan_markdown(plan, template_body))
    _write_text(preview_path, render_plan_html(plan))
    _write_text(json_path, json_dumps(plan))
    docx_path, template_warning = _build_plan_docx(template_meta, plan, result_dir)

    validation = validate_generated_plan(plan, template_meta["formatRules"])
    execute(
        """
        UPDATE t_teaching_plan
        SET course_name = ?, course_type = ?, outline_json = ?, goals_text = ?, key_points = ?,
            validate_status = ?, file_path = ?, preview_path = ?, content_json = ?
        WHERE plan_id = ?
        """,
        (
            plan["course_name"],
            plan.get("course_type") or row["course_type"],
            json_dumps(plan["outline"]),
            "\n".join(plan["goals"]),
            "；".join(plan["focus_points"]),
            validation["status"],
            str(docx_path),
            str(preview_path),
            json_dumps(plan),
            plan_id,
        ),
    )
    _create_validation_record(plan_id, "PLAN", validation)
    result_meta = {
        "targetType": "PLAN",
        "targetId": plan_id,
        "previewUrl": f"/api/v1/previews/plan/{plan_id}",
        "downloadHint": str(docx_path),
        "score": validation["score"],
        "validationStatus": validation["status"],
        "files": {
            "markdown": str(markdown_path),
            "html": str(preview_path),
            "json": str(json_path),
            "docx": str(docx_path),
        },
    }
    if template_warning:
        result_meta["warnings"] = [template_warning]
    _refresh_task_result(row["task_id"], docx_path, result_meta)
    record_audit(user_row["user_id"], "CONTENT_EDIT", "PLAN", plan_id, "SUCCESS", "人工编辑教学方案并重新生成预览")
    return get_generated_content(plan_id, "PLAN", user_row)


def _update_courseware_content(courseware_id, payload, user_row):
    row = fetch_one("SELECT * FROM t_courseware WHERE courseware_id = ?", (courseware_id,))
    if not row:
        raise ServiceError(2003, "教学课件不存在", 404)
    incoming = _require_content_object(payload)
    courseware = json_loads(row["content_json"], {})
    courseware.update(incoming)
    slides = courseware.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ServiceError(1000, "slides 不能为空", 400)
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            raise ServiceError(1000, f"slides[{index}] 必须是对象", 400)
        slide["title"] = str(slide.get("title", "")).strip()
        slide["bullets"] = _normalize_text_list(slide.get("bullets"))
    courseware["slide_count"] = len(slides)

    task, template_meta = _load_task_template(row["task_id"])
    result_dir = _ensure_result_dir(task["task_id"])
    preview_path = result_dir / "courseware_preview.html"
    json_path = result_dir / "courseware.json"
    outline_path = result_dir / "courseware_outline.txt"
    _write_text(preview_path, render_courseware_html(courseware))
    _write_text(json_path, json_dumps(courseware))
    _write_text(outline_path, "\n".join(courseware_lines(courseware)))
    presentation_path, presentation_warning = _build_courseware_presentation(template_meta, courseware, result_dir)

    validation = validate_generated_courseware(courseware, template_meta["formatRules"])
    execute(
        """
        UPDATE t_courseware
        SET slide_count = ?, theme_name = ?, file_path = ?, preview_path = ?, validate_status = ?,
            slides_json = ?, content_json = ?
        WHERE courseware_id = ?
        """,
        (
            courseware["slide_count"],
            courseware.get("theme_name") or row["theme_name"],
            str(presentation_path or json_path),
            str(preview_path),
            validation["status"],
            json_dumps(slides),
            json_dumps(courseware),
            courseware_id,
        ),
    )
    _create_validation_record(courseware_id, "COURSEWARE", validation)
    result_meta = {
        "targetType": "COURSEWARE",
        "targetId": courseware_id,
        "previewUrl": f"/api/v1/previews/courseware/{courseware_id}",
        "downloadHint": str(json_path),
        "slideCount": courseware["slide_count"],
        "score": validation["score"],
        "validationStatus": validation["status"],
        "files": {
            "html": str(preview_path),
            "json": str(json_path),
            "outline": str(outline_path),
            "pptx": str(presentation_path) if presentation_path else "",
        },
    }
    if presentation_warning:
        result_meta["warnings"] = [presentation_warning]
    _refresh_task_result(row["task_id"], presentation_path or json_path, result_meta)
    record_audit(user_row["user_id"], "CONTENT_EDIT", "COURSEWARE", courseware_id, "SUCCESS", "人工编辑教学课件并重新生成预览")
    return get_generated_content(courseware_id, "COURSEWARE", user_row)


def process_task(task_id):
    task = fetch_one("SELECT * FROM t_generation_task WHERE task_id = ?", (task_id,))
    if not task:
        return
    if task["status"] == "CANCELED":
        return

    try:
        _update_task(task_id, "RUNNING", 10)
        if _is_task_canceled(task_id):
            return
        _update_task(task_id, "GENERATING", 40)
        if _is_task_canceled(task_id):
            return
        if task["task_type"] == "PLAN":
            _update_task(task_id, "VALIDATING", 70)
            if _is_task_canceled(task_id):
                return
            result_meta, result_path = _build_plan_result(task)
        elif task["task_type"] == "COURSEWARE":
            _update_task(task_id, "VALIDATING", 70)
            if _is_task_canceled(task_id):
                return
            result_meta, result_path = _build_courseware_result(task)
        else:
            raise ServiceError(5000, "未知任务类型", 500)
        if _is_task_canceled(task_id):
            return
        _update_task(task_id, "SUCCESS", 100, result_path=result_path, result_meta=result_meta)
    except ServiceError as exc:
        _update_task(task_id, "FAILED", 100, error_message=exc.message)
    except Exception as exc:
        _update_task(task_id, "FAILED", 100, error_message=str(exc))


def validate_target(target_id, target_type, user_row=None):
    normalized_type = normalize_target_type(target_type)
    _ensure_target_access(normalized_type, target_id, user_row)
    if normalized_type == "PLAN":
        row = fetch_one("SELECT * FROM t_teaching_plan WHERE plan_id = ?", (target_id,))
        if not row:
            raise ServiceError(2003, "教学方案不存在", 404)
        plan = json_loads(row["content_json"], {})
        validation = validate_generated_plan(plan, DEFAULT_TEMPLATE_RULES.get(row["course_type"], DEFAULT_TEMPLATE_RULES["THEORY"]))
    else:
        row = fetch_one("SELECT * FROM t_courseware WHERE courseware_id = ?", (target_id,))
        if not row:
            raise ServiceError(2003, "课件不存在", 404)
        courseware = json_loads(row["content_json"], {})
        validation = validate_generated_courseware(courseware, DEFAULT_TEMPLATE_RULES["TRAINING"])

    _create_validation_record(target_id, normalized_type, validation)
    latest = fetch_one(
        """
        SELECT * FROM t_validation_result
        WHERE target_id = ? AND target_type = ?
        ORDER BY result_id DESC
        LIMIT 1
        """,
        (target_id, normalized_type),
    )
    return _serialize_validation(latest)


def save_resource(upload_file, resource_type, tags, user_id):
    if not isinstance(upload_file, FileStorage) or not upload_file.filename:
        raise ServiceError(1000, "请上传资源文件", 400)
    normalized_type = normalize_resource_type(resource_type)
    suffix = Path(upload_file.filename).suffix.lower()
    if suffix not in current_app.config["ALLOWED_RESOURCE_EXTENSIONS"]:
        raise ServiceError(1000, "不支持的资源文件格式", 415)

    resource_id = make_id("RES")
    destination = Path(current_app.config["RESOURCE_DIR"]) / f"{resource_id}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    upload_file.save(destination)
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    execute(
        """
        INSERT INTO t_resource(resource_id, resource_type, resource_name, tags, file_path, checksum, uploader_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resource_id,
            normalized_type,
            upload_file.filename,
            ",".join(tags),
            str(destination),
            checksum,
            user_id,
            now_text(),
        ),
    )
    record_audit(user_id, "RESOURCE_UPLOAD", "RESOURCE", resource_id, "SUCCESS", "上传教学资源")
    row = fetch_one("SELECT * FROM t_resource WHERE resource_id = ?", (resource_id,))
    return _serialize_resource(row)


def _detect_target(target_id):
    plan = fetch_one("SELECT * FROM t_teaching_plan WHERE plan_id = ?", (target_id,))
    if plan:
        return "PLAN", plan
    courseware = fetch_one("SELECT * FROM t_courseware WHERE courseware_id = ?", (target_id,))
    if courseware:
        return "COURSEWARE", courseware
    raise ServiceError(2003, "导出目标不存在", 404)


def _copy_export(source_path, export_name):
    source = Path(source_path)
    if not source.exists():
        raise ServiceError(4001, "导出源文件不存在", 500)
    destination = Path(current_app.config["EXPORT_DIR"]) / export_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def _export_plan(plan_row, requested_format):
    plan = json_loads(plan_row["content_json"], {})
    requested_format = requested_format.lower()
    if requested_format in {"doc", "docx", "word"}:
        source = Path(plan_row["file_path"])
        return _copy_export(source, f"{plan_row['plan_id']}.docx"), "docx"
    if requested_format in {"html"}:
        return _copy_export(plan_row["preview_path"], f"{plan_row['plan_id']}.html"), "html"
    if requested_format in {"json"}:
        source = Path(plan_row["preview_path"]).with_name("plan.json")
        return _copy_export(source, f"{plan_row['plan_id']}.json"), "json"
    if requested_format in {"md", "markdown", "txt"}:
        source = Path(plan_row["preview_path"]).with_name("plan.md")
        extension = "md" if requested_format != "txt" else "txt"
        if extension == "txt":
            temp_txt = Path(current_app.config["EXPORT_DIR"]) / f"{plan_row['plan_id']}.txt"
            temp_txt.write_text("\n".join(teaching_plan_lines(plan)), encoding="utf-8")
            return temp_txt, "txt"
        return _copy_export(source, f"{plan_row['plan_id']}.md"), "md"
    if requested_format in {"pdf"}:
        target = Path(current_app.config["EXPORT_DIR"]) / f"{plan_row['plan_id']}.pdf"
        try:
            docx_to_pdf(plan_row["file_path"], target)
        except Exception as exc:
            raise ServiceError(4001, "教学方案 PDF 导出失败，请确认本机 Word 自动化可用", 500, str(exc)) from exc
        return target, "pdf"
    raise ServiceError(4001, "当前教学方案暂不支持该导出格式", 400)


def _export_courseware(courseware_row, requested_format):
    courseware = json_loads(courseware_row["content_json"], {})
    slides = courseware["slides"]
    requested_format = requested_format.lower()
    source_path = Path(courseware_row["file_path"])
    if requested_format in {"html"}:
        return _copy_export(courseware_row["preview_path"], f"{courseware_row['courseware_id']}.html"), "html"
    if requested_format in {"json"}:
        source = source_path if source_path.suffix.lower() == ".json" else Path(courseware_row["preview_path"]).with_name("courseware.json")
        return _copy_export(source, f"{courseware_row['courseware_id']}.json"), "json"
    if requested_format in {"txt"}:
        target = Path(current_app.config["EXPORT_DIR"]) / f"{courseware_row['courseware_id']}.txt"
        target.write_text("\n".join(courseware_lines(courseware)), encoding="utf-8")
        return target, "txt"
    if requested_format in {"pdf"}:
        target = Path(current_app.config["EXPORT_DIR"]) / f"{courseware_row['courseware_id']}.pdf"
        try:
            if source_path.suffix.lower() == ".pptx" and source_path.exists():
                pptx_to_pdf(source_path, target)
            else:
                temp_pptx = Path(current_app.config["EXPORT_DIR"]) / f"{courseware_row['courseware_id']}_temp.pptx"
                slides_to_pptx(slides, temp_pptx)
                pptx_to_pdf(temp_pptx, target)
        except Exception as exc:
            raise ServiceError(4001, "教学课件 PDF 导出失败，请确认本机 PowerPoint 自动化可用", 500, str(exc)) from exc
        finally:
            if "temp_pptx" in locals() and temp_pptx.exists():
                temp_pptx.unlink()
        return target, "pdf"
    if requested_format in {"ppt", "pptx"}:
        target = Path(current_app.config["EXPORT_DIR"]) / f"{courseware_row['courseware_id']}.pptx"
        try:
            if source_path.suffix.lower() == ".pptx" and source_path.exists():
                shutil.copyfile(source_path, target)
            else:
                slides_to_pptx(slides, target)
        except Exception as exc:
            raise ServiceError(4001, "教学课件 PPTX 导出失败，请确认本机 PowerPoint 自动化可用", 500, str(exc)) from exc
        return target, "pptx"
    raise ServiceError(4001, "当前课件暂不支持该导出格式", 400)


def create_export(target_id, requested_format, expiry_days, share_scope, user_id, max_downloads=0):
    user_row = get_user_by_id(user_id)
    target_type, row = _detect_target(target_id)
    _ensure_target_access(target_type, target_id, user_row)
    expiry_days = int(expiry_days or current_app.config["DEFAULT_SHARE_DAYS"])
    expiry_time = datetime.now() + timedelta(days=max(1, expiry_days))
    normalized_scope = str(share_scope or "private").strip().lower()
    if normalized_scope not in {"private", "public", "course"}:
        normalized_scope = "private"
    try:
        max_downloads = max(0, int(max_downloads or 0))
    except (TypeError, ValueError):
        max_downloads = 0

    if target_type == "PLAN":
        file_path, actual_format = _export_plan(row, requested_format)
    else:
        file_path, actual_format = _export_courseware(row, requested_format)

    share_token = uuid.uuid4().hex
    export_id = execute(
        """
        INSERT INTO t_export_record(target_id, target_type, format, actual_format, file_path, share_token, share_url,
            share_scope, max_downloads, expiry_time, download_count, creator_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            target_id,
            target_type,
            requested_format.lower(),
            actual_format,
            str(file_path),
            share_token,
            f"/share/{share_token}",
            normalized_scope,
            max_downloads,
            expiry_time.strftime("%Y-%m-%d %H:%M:%S"),
            user_id,
            now_text(),
        ),
    )
    record_audit(user_id, "EXPORT_CREATE", target_type, target_id, "SUCCESS", f"导出为 {requested_format}/{actual_format}")
    return {
        "exportId": export_id,
        "targetId": target_id,
        "targetType": target_type,
        "format": requested_format.lower(),
        "actualFormat": actual_format,
        "downloadUrl": f"/api/v1/exports/{export_id}/download",
        "shareUrl": f"/share/{share_token}",
        "fileSize": Path(file_path).stat().st_size,
        "shareScope": normalized_scope,
        "maxDownloads": max_downloads,
        "expiryTime": expiry_time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_export_record(export_id, user_row=None):
    row = fetch_one("SELECT * FROM t_export_record WHERE export_id = ?", (export_id,))
    if not row:
        raise ServiceError(4001, "导出记录不存在", 404)
    if user_row and row.get("creator_id") and int(row["creator_id"]) != int(user_row["user_id"]) and not _can_manage_all(user_row):
        raise ServiceError(1002, "当前用户无权下载该导出文件", 403)
    return row


def get_export_record_by_token(share_token):
    row = fetch_one("SELECT * FROM t_export_record WHERE share_token = ?", (share_token,))
    if not row:
        raise ServiceError(4001, "分享链接不存在", 404)
    return row


def increase_download_count(export_id):
    execute(
        "UPDATE t_export_record SET download_count = download_count + 1 WHERE export_id = ?",
        (export_id,),
    )


def ensure_not_expired(export_row):
    expiry = datetime.strptime(export_row["expiry_time"], "%Y-%m-%d %H:%M:%S")
    if expiry < datetime.now():
        raise ServiceError(4001, "分享链接已过期", 410)
    max_downloads = int(export_row.get("max_downloads") or 0)
    if max_downloads and int(export_row["download_count"] or 0) >= max_downloads:
        raise ServiceError(4001, "分享链接下载次数已用完", 410)


def get_preview_file(target_type, target_id, user_row=None):
    normalized_type = normalize_target_type(target_type)
    _ensure_target_access(normalized_type, target_id, user_row)
    if normalized_type == "PLAN":
        row = fetch_one("SELECT preview_path FROM t_teaching_plan WHERE plan_id = ?", (target_id,))
    else:
        row = fetch_one("SELECT preview_path FROM t_courseware WHERE courseware_id = ?", (target_id,))
    if not row:
        raise ServiceError(2003, "预览目标不存在", 404)
    preview_path = Path(row["preview_path"])
    if not preview_path.exists():
        raise ServiceError(2003, "预览文件不存在", 404)
    return preview_path
