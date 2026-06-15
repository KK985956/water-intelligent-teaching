import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from .ai_generation import build_courseware_with_ai
from .documents import build_courseware, build_teaching_plan, validate_courseware, validate_plan
from .errors import ServiceError


def _service_base_url():
    return str(current_app.config.get("GENERATION_SERVICE_URL") or "").rstrip("/")


def _post_to_generation_service(path, payload):
    base_url = _service_base_url()
    if not base_url:
        return None

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{base_url}{path}",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    timeout = int(current_app.config.get("GENERATION_SERVICE_TIMEOUT_SECONDS") or 30)
    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise ServiceError(5001, f"生成服务调用失败：HTTP {exc.code} {detail}", 502) from exc
    except URLError as exc:
        raise ServiceError(5001, f"生成服务不可用：{exc.reason}", 502) from exc

    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ServiceError(5001, "生成服务返回了无法解析的 JSON", 502) from exc

    if payload.get("code", 0) != 0:
        raise ServiceError(5001, payload.get("message") or "生成服务返回失败", 502, payload)
    return payload.get("data", payload)


def generate_teaching_plan(params, template_meta):
    remote_result = _post_to_generation_service(
        "/api/v1/generate/plan",
        {"params": params, "templateMeta": template_meta},
    )
    if remote_result is not None:
        return remote_result["plan"]
    return build_teaching_plan(params, template_meta)


def generate_courseware(plan, template_meta, resources):
    remote_result = _post_to_generation_service(
        "/api/v1/generate/courseware",
        {"plan": plan, "templateMeta": template_meta, "resources": resources},
    )
    if remote_result is not None:
        return remote_result["courseware"]
    ai_result = build_courseware_with_ai(plan, template_meta, resources)
    if ai_result is not None:
        return ai_result
    return build_courseware(plan, template_meta, resources)


def validate_generated_plan(plan, rules):
    remote_result = _post_to_generation_service(
        "/api/v1/validate/plan",
        {"plan": plan, "rules": rules},
    )
    if remote_result is not None:
        return remote_result["validation"]
    return validate_plan(plan, rules)


def validate_generated_courseware(courseware, rules):
    remote_result = _post_to_generation_service(
        "/api/v1/validate/courseware",
        {"courseware": courseware, "rules": rules},
    )
    if remote_result is not None:
        return remote_result["validation"]
    return validate_courseware(courseware, rules)
