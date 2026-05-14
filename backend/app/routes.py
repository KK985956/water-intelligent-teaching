from pathlib import Path

from flask import jsonify, request, send_file, send_from_directory

from .auth import current_user, require_auth
from .services import (
    authenticate_user,
    cancel_task,
    create_user,
    create_courseware_task,
    create_export,
    create_plan_task,
    create_template,
    ensure_not_expired,
    get_export_record,
    get_export_record_by_token,
    get_generated_content,
    get_preview_file,
    get_runtime_context,
    get_task,
    get_template_detail,
    increase_download_count,
    list_audit_logs,
    list_roles,
    list_resources,
    list_tasks,
    list_templates,
    list_users,
    retry_task,
    rollback_template_version,
    save_resource,
    update_generated_content,
    update_user,
    upload_template_version,
    validate_target,
)


def ok(data=None, message="ok"):
    return jsonify({"code": 0, "message": message, "data": {} if data is None else data})


def register_routes(app):
    frontend_dir = Path(app.root_path).parent / "web"

    @app.get("/")
    def index():
        return send_from_directory(frontend_dir, "dashboard.html")

    @app.get("/assets/<path:filename>")
    def frontend_assets(filename):
        return send_from_directory(frontend_dir / "assets", filename)

    @app.get("/api/v1/health")
    def health():
        return ok({"status": "UP"})

    @app.post("/api/v1/auth/login")
    def login():
        payload = request.get_json(silent=True) or request.form.to_dict()
        result = authenticate_user(
            payload.get("username", ""),
            payload.get("password", ""),
            payload.get("captcha", ""),
            request.remote_addr or "",
        )
        return ok(result)

    @app.get("/api/v1/runtime/context")
    @require_auth()
    def runtime_context():
        return ok(get_runtime_context(current_user()))

    @app.get("/api/v1/templates")
    @require_auth("templates:read")
    def templates():
        result = list_templates(
            template_type=request.args.get("type"),
            keyword=request.args.get("keyword"),
            page=request.args.get("page", 1),
            size=request.args.get("size", 10),
        )
        return ok(result)

    @app.post("/api/v1/templates/upload")
    @require_auth("templates:write")
    def template_upload():
        user = current_user()
        file_obj = request.files.get("file")
        result = create_template(
            file_obj,
            request.form.get("type", ""),
            request.form.get("name", ""),
            request.form.get("rulesJson", ""),
            user["user_id"],
        )
        return ok(result, "模板上传成功")

    @app.get("/api/v1/templates/<template_id>")
    @require_auth("templates:read")
    def template_detail(template_id):
        return ok(get_template_detail(template_id))

    @app.post("/api/v1/templates/<template_id>/versions")
    @require_auth("templates:write")
    def template_version_upload(template_id):
        user = current_user()
        result = upload_template_version(
            template_id,
            request.files.get("file"),
            request.form.get("changeLog", ""),
            request.form.get("rulesJson", ""),
            user["user_id"],
            request.form.get("name", ""),
        )
        return ok(result, "模板新版本上传成功")

    @app.post("/api/v1/templates/<template_id>/rollback")
    @require_auth("templates:write")
    def template_rollback(template_id):
        user = current_user()
        payload = request.get_json(silent=True) or {}
        result = rollback_template_version(template_id, payload.get("versionNo"), user["user_id"])
        return ok(result, "模板已回滚")

    @app.post("/api/v1/generation/plans")
    @require_auth("generation:run")
    def generate_plan():
        user = current_user()
        payload = request.get_json(silent=True) or {}
        result = create_plan_task(user["user_id"], payload)
        return ok(result, "任务已创建")

    @app.post("/api/v1/generation/coursewares")
    @require_auth("generation:run")
    def generate_courseware():
        user = current_user()
        payload = request.get_json(silent=True) or {}
        result = create_courseware_task(user["user_id"], payload)
        return ok(result, "任务已创建")

    @app.get("/api/v1/tasks/<task_id>")
    @require_auth("generation:run")
    def task_detail(task_id):
        return ok(get_task(task_id, current_user()))

    @app.post("/api/v1/tasks/<task_id>/cancel")
    @require_auth("generation:run")
    def task_cancel(task_id):
        return ok(cancel_task(task_id, current_user()), "任务已取消")

    @app.post("/api/v1/tasks/<task_id>/retry")
    @require_auth("generation:run")
    def task_retry(task_id):
        return ok(retry_task(task_id, current_user()), "任务已重新入队")

    @app.get("/api/v1/tasks")
    @require_auth("generation:run")
    def task_list():
        user = current_user()
        result = list_tasks(
            user["user_id"],
            status=request.args.get("status"),
            limit=request.args.get("limit", 20),
        )
        return ok(result)

    @app.get("/api/v1/roles")
    @require_auth("users:manage")
    def role_list():
        return ok(list_roles())

    @app.get("/api/v1/users")
    @require_auth("users:manage")
    def user_list():
        result = list_users(
            keyword=request.args.get("keyword"),
            role_code=request.args.get("roleCode"),
            status=request.args.get("status"),
            page=request.args.get("page", 1),
            size=request.args.get("size", 20),
        )
        return ok(result)

    @app.post("/api/v1/users")
    @require_auth("users:manage")
    def user_create():
        user = current_user()
        payload = request.get_json(silent=True) or {}
        return ok(create_user(payload, user["user_id"]), "用户创建成功")

    @app.patch("/api/v1/users/<int:user_id>")
    @require_auth("users:manage")
    def user_update(user_id):
        user = current_user()
        payload = request.get_json(silent=True) or {}
        return ok(update_user(user_id, payload, user["user_id"]), "用户更新成功")

    @app.get("/api/v1/audit-logs")
    @require_auth("logs:read")
    def audit_logs():
        return ok(
            list_audit_logs(
                keyword=request.args.get("keyword"),
                action=request.args.get("action"),
                page=request.args.get("page", 1),
                size=request.args.get("size", 20),
            )
        )

    @app.get("/api/v1/content/<target_type>/<target_id>")
    @require_auth("generation:run")
    def content_detail(target_type, target_id):
        return ok(get_generated_content(target_id, target_type, current_user()))

    @app.patch("/api/v1/content/<target_type>/<target_id>")
    @require_auth("content:edit")
    def content_update(target_type, target_id):
        payload = request.get_json(silent=True) or {}
        return ok(update_generated_content(target_id, target_type, payload, current_user()), "内容已更新")

    @app.post("/api/v1/validation/format")
    @require_auth("validation:run")
    def validation():
        payload = request.get_json(silent=True) or {}
        return ok(validate_target(payload.get("targetId", ""), payload.get("targetType", ""), current_user()))

    @app.get("/api/v1/resources")
    @require_auth("resources:read")
    def resource_list():
        result = list_resources(
            resource_type=request.args.get("type"),
            keyword=request.args.get("keyword"),
            page=request.args.get("page", 1),
            size=request.args.get("size", 20),
        )
        return ok(result)

    @app.post("/api/v1/resources/upload")
    @require_auth("resources:write")
    def resource_upload():
        user = current_user()
        file_obj = request.files.get("file")
        tags = [item.strip() for item in request.form.get("tags", "").split(",") if item.strip()]
        result = save_resource(file_obj, request.form.get("resourceType", ""), tags, user["user_id"])
        return ok(result, "资源上传成功")

    @app.post("/api/v1/exports")
    @require_auth("exports:write")
    def export_target():
        user = current_user()
        payload = request.get_json(silent=True) or {}
        result = create_export(
            payload.get("targetId", ""),
            payload.get("format", ""),
            payload.get("expiryDays", app.config["DEFAULT_SHARE_DAYS"]),
            payload.get("shareScope", "private"),
            user["user_id"],
            payload.get("maxDownloads", 0),
        )
        return ok(result, "导出成功")

    @app.get("/api/v1/exports/<int:export_id>/download")
    @require_auth("generation:run")
    def download_export(export_id):
        export_row = get_export_record(export_id, current_user())
        ensure_not_expired(export_row)
        increase_download_count(export_id)
        file_path = Path(export_row["file_path"])
        return send_file(file_path, as_attachment=True, download_name=file_path.name)

    @app.get("/api/v1/previews/<target_type>/<target_id>")
    @require_auth("generation:run")
    def preview(target_type, target_id):
        preview_file = get_preview_file(target_type, target_id, current_user())
        return send_file(preview_file, mimetype="text/html; charset=utf-8")

    @app.get("/share/<share_token>")
    def share_download(share_token):
        export_row = get_export_record_by_token(share_token)
        ensure_not_expired(export_row)
        increase_download_count(export_row["export_id"])
        file_path = Path(export_row["file_path"])
        return send_file(file_path, as_attachment=True, download_name=file_path.name)
