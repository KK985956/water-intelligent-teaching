from functools import wraps

from flask import current_app, g, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from .errors import ServiceError


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password, password_hash):
    return check_password_hash(password_hash, password)


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="water-teaching-auth")


def issue_token(user):
    payload = {
        "user_id": user["user_id"],
        "username": user["username"],
        "role_code": user["role_code"],
    }
    return _serializer().dumps(payload)


def read_token(token):
    try:
        return _serializer().loads(
            token,
            max_age=current_app.config["TOKEN_TTL_SECONDS"],
        )
    except SignatureExpired as exc:
        raise ServiceError(1001, "登录凭证已过期，请重新登录", 401) from exc
    except BadSignature as exc:
        raise ServiceError(1001, "无效的登录凭证", 401) from exc


def current_user():
    return getattr(g, "current_user", None)


def require_auth(permission=None):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            from .services import get_user_by_id, user_has_permission

            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                raise ServiceError(1001, "缺少 Bearer Token", 401)

            token = auth_header.split(" ", 1)[1].strip()
            payload = read_token(token)
            user = get_user_by_id(payload["user_id"])
            if not user or int(user["status"]) != 1:
                raise ServiceError(1001, "当前用户不可用，请重新登录", 401)

            if permission and not user_has_permission(user["role_code"], permission):
                raise ServiceError(1002, "当前角色无该操作权限", 403)

            g.current_user = user
            return view_func(*args, **kwargs)

        return wrapped

    return decorator
