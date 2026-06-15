import base64
import json
from pathlib import Path

from flask import current_app

from .documents import build_courseware


ALLOWED_LAYOUTS = {
    "cover",
    "section",
    "two_column",
    "image_right",
    "process",
    "case_card",
    "summary",
}


def ai_courseware_enabled():
    return bool(current_app.config.get("AI_COURSEWARE_ENABLED")) and bool(current_app.config.get("OPENAI_API_KEY"))


def _openai_client():
    try:
        from openai import OpenAI
    except Exception:
        return None

    kwargs = {"api_key": current_app.config.get("OPENAI_API_KEY")}
    if current_app.config.get("OPENAI_BASE_URL"):
        kwargs["base_url"] = current_app.config["OPENAI_BASE_URL"]
    return OpenAI(**kwargs)


def _response_text(response):
    text = getattr(response, "output_text", None)
    if text:
        return text

    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)
    return "\n".join(chunks)


def _courseware_schema():
    return {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "theme_name": {"type": "string"},
            "slides": {
                "type": "array",
                "minItems": 8,
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "title": {"type": "string"},
                        "subtitle": {"type": "string"},
                        "layout": {"type": "string"},
                        "bullets": {"type": "array", "items": {"type": "string"}},
                        "image_prompt": {"type": "string"},
                        "speaker_notes": {"type": "string"},
                        "teacher_activity": {"type": "string"},
                        "student_activity": {"type": "string"},
                    },
                    "required": ["title", "layout", "bullets"],
                },
            },
        },
        "required": ["theme_name", "slides"],
    }


def _build_prompt(plan, template_meta, resources):
    resource_names = [item.get("resourceName") or item.get("resource_name") or "" for item in resources]
    return "\n".join(
        [
            "你是水利类课程教学课件设计专家。请生成可直接用于 PowerPoint 的中文教学课件 JSON。",
            "课件必须服务课堂教学，不要只给普通文字提纲；每页都要体现教师怎么教、学生怎么学、为什么这样安排。",
            "输出必须是 JSON，不要 Markdown、解释或多余文字。",
            "JSON 字段：theme_name, slides。slides 每项包含 title, subtitle, layout, bullets, image_prompt, speaker_notes, teacher_activity, student_activity。",
            "slides 必须 8 到 12 页，包含封面、教学目标、重点难点、课堂结构、至少 2 页案例/图解/流程页、课堂练习、总结作业。",
            "layout 只能从 cover, section, two_column, image_right, process, case_card, summary 中选择。",
            "bullets 每页 3 到 5 条，每条必须包含教学动作、核心概念或水利工程案例信息，避免空泛口号。",
            "speaker_notes 要写成教师可照着讲的提示，包含追问、纠错或课堂组织建议。",
            "image_prompt 要适合生图，描述画面主体、教学场景、图解元素和 PPT 风格，不要写抽象口号。",
            f"课程名称：{plan.get('course_name', '')}",
            f"模板名称：{template_meta.get('templateName') or template_meta.get('template_name') or ''}",
            f"授课对象：{plan.get('audience', '')}",
            f"课时：{plan.get('hours', '')}",
            f"教学目标：{json.dumps(plan.get('goals', []), ensure_ascii=False)}",
            f"重点：{json.dumps(plan.get('focus_points', []), ensure_ascii=False)}",
            f"难点：{json.dumps(plan.get('difficult_points', []), ensure_ascii=False)}",
            f"教学流程：{json.dumps(plan.get('outline', []), ensure_ascii=False)}",
            f"案例：{json.dumps(plan.get('cases', []), ensure_ascii=False)}",
            f"资源：{json.dumps([name for name in resource_names if name], ensure_ascii=False)}",
        ]
    )


def _safe_string(value, fallback=""):
    text = str(value or "").strip()
    return text or fallback


def normalize_ai_courseware(payload, fallback_courseware):
    if not isinstance(payload, dict):
        return None

    raw_slides = payload.get("slides")
    if not isinstance(raw_slides, list) or not raw_slides:
        return None

    slides = []
    for index, raw_slide in enumerate(raw_slides, start=1):
        if not isinstance(raw_slide, dict):
            continue

        title = _safe_string(raw_slide.get("title"), f"Slide {index}")
        bullets = raw_slide.get("bullets")
        if not isinstance(bullets, list):
            bullets = []
        clean_bullets = [_safe_string(item) for item in bullets if _safe_string(item)]
        if not clean_bullets:
            clean_bullets = [title]
        teacher_activity = _safe_string(raw_slide.get("teacher_activity"))
        student_activity = _safe_string(raw_slide.get("student_activity"))
        speaker_notes = _safe_string(raw_slide.get("speaker_notes"))
        activity_notes = []
        if teacher_activity:
            activity_notes.append(f"教师活动：{teacher_activity}")
        if student_activity:
            activity_notes.append(f"学生活动：{student_activity}")
        if activity_notes:
            speaker_notes = "\n".join(activity_notes + ([speaker_notes] if speaker_notes else []))

        layout = _safe_string(raw_slide.get("layout"), "two_column")
        if layout not in ALLOWED_LAYOUTS:
            layout = "two_column"

        slides.append(
            {
                "title": title,
                "subtitle": _safe_string(raw_slide.get("subtitle")),
                "layout": layout,
                "bullets": clean_bullets[:6],
                "image_prompt": _safe_string(raw_slide.get("image_prompt")),
                "speaker_notes": speaker_notes,
                "teacher_activity": teacher_activity,
                "student_activity": student_activity,
                "image_path": _safe_string(raw_slide.get("image_path")),
            }
        )

    if not slides:
        return None

    courseware = dict(fallback_courseware)
    courseware["theme_name"] = _safe_string(payload.get("theme_name"), fallback_courseware.get("theme_name", ""))
    courseware["template_name"] = fallback_courseware.get("template_name", "")
    courseware["slides"] = slides
    courseware["slide_count"] = len(slides)
    courseware["ai_enhanced"] = True
    return courseware


def _parse_json_response(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def generate_slide_image(prompt, output_path, client=None):
    if not current_app.config.get("OPENAI_IMAGE_ENABLED"):
        return None
    if not prompt:
        return None

    client = client or _openai_client()
    if client is None:
        return None

    try:
        response = client.responses.create(
            model=current_app.config.get("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            input=prompt,
            tools=[{"type": "image_generation"}],
        )
    except Exception:
        return None

    image_data = None
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", "") == "image_generation_call":
            image_data = getattr(item, "result", None)
            break
    if not image_data:
        return None

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(image_data))
    return output_path


def build_courseware_with_ai(plan, template_meta, resources, client=None):
    if not ai_courseware_enabled():
        return None

    fallback_courseware = build_courseware(plan, template_meta, resources)
    client = client or _openai_client()
    if client is None:
        return None

    try:
        response = client.responses.create(
            model=current_app.config.get("OPENAI_TEXT_MODEL", "gpt-4.1-mini"),
            input=[
                {
                    "role": "system",
                    "content": "你只输出满足要求的 JSON。不要输出 Markdown、解释或多余文字。",
                },
                {"role": "user", "content": _build_prompt(plan, template_meta, resources)},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "courseware",
                    "schema": _courseware_schema(),
                    "strict": False,
                }
            },
        )
        payload = _parse_json_response(_response_text(response))
        return normalize_ai_courseware(payload, fallback_courseware)
    except Exception:
        return None
