import html
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import OrderedDict
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from flask import current_app
from jinja2 import Template


PLACEHOLDER_PATTERN = re.compile(r"{{\s*([^{}]+?)\s*}}")

DEFAULT_PLAN_TEMPLATE = """# {{ course_name }}教学方案

## 一、课程基本信息
- 模板名称：{{ template_name }}
- 课程类型：{{ course_type_label }}
- 授课对象：{{ audience }}
- 总课时：{{ hours }} 课时
- 生成时间：{{ generated_at }}

## 二、教学目标
{% for item in goals %}
- {{ item }}
{% endfor %}

## 三、教学重难点
- 重点：{{ focus_points | join("；") }}
- 难点：{{ difficult_points | join("；") }}

## 四、教学资源与案例
{% for item in cases %}
- {{ item }}
{% endfor %}

## 五、教学流程
{% for section in outline %}
### {{ loop.index }}. {{ section.title }}（{{ section.duration }}）
- 教学内容：{{ section.content }}
- 教学方法：{{ section.method }}
- 对应知识点：{{ section.knowledge_points | join("；") }}
{% endfor %}

## 六、课堂练习
{% for item in exercises %}
- {{ item }}
{% endfor %}

## 七、课后任务
{% for item in homework %}
- {{ item }}
{% endfor %}

## 八、教学总结
{{ summary }}
"""

COURSE_TYPE_LABELS = {
    "THEORY": "理论课",
    "PRACTICE": "实训课",
    "TRAINING": "培训课",
    "REVIEW": "复习课",
}


def load_knowledge_base():
    knowledge_path = Path(current_app.config["DATA_DIR"]) / "knowledge_base.json"
    with knowledge_path.open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def extract_template_text(file_path):
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix in {".doc", ".ppt"}:
        return "legacy-binary-format"
    if suffix not in {".docx", ".pptx"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            if suffix == ".docx":
                xml_names = [name for name in names if name.startswith("word/") and name.endswith(".xml")]
            else:
                xml_names = [name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")]

            texts = []
            for name in xml_names:
                with archive.open(name) as xml_file:
                    root = ET.fromstring(xml_file.read())
                    for node in root.iter():
                        if node.text and node.tag.endswith("}t"):
                            texts.append(node.text)
            return "\n".join(texts)
    except Exception:
        return ""


def extract_placeholders(template_text):
    ordered = OrderedDict()
    for match in PLACEHOLDER_PATTERN.finditer(template_text or ""):
        ordered.setdefault(match.group(1).strip(), True)
    return list(ordered.keys())


def _match_entry(knowledge_base, course_name, goals, focus_points):
    text = " ".join([course_name] + goals + focus_points)
    best_entry = None
    best_score = -1
    for entry in knowledge_base["catalog"]:
        score = 0
        for keyword in entry["keywords"]:
            if keyword and keyword in text:
                score += 2
            if keyword and keyword in course_name:
                score += 3
        if entry["name"] == course_name:
            score += 5
        if score > best_score:
            best_score = score
            best_entry = entry
    return best_entry or knowledge_base["default"]


def _apportion_minutes(total_minutes, weights):
    total_weight = sum(weights)
    raw = [total_minutes * weight / total_weight for weight in weights]
    floors = [math.floor(item) for item in raw]
    remainder = total_minutes - sum(floors)
    order = sorted(range(len(raw)), key=lambda idx: raw[idx] - floors[idx], reverse=True)
    for index in order[:remainder]:
        floors[index] += 1
    return floors


def _format_duration(minutes):
    if minutes % 45 == 0:
        return f"{minutes // 45}课时（{minutes}分钟）"
    return f"{minutes}分钟"


def build_teaching_plan(params, template_meta):
    knowledge_base = load_knowledge_base()
    course_name = params["courseName"].strip()
    template_type = template_meta.get("template_type") or template_meta.get("templateType")
    hours = int(params["hours"])
    audience = params["audience"].strip()
    goals = [item.strip() for item in params.get("goals", []) if str(item).strip()]
    if not goals:
        goals = ["理解课程核心概念", "能够结合水利场景完成知识迁移"]
    focus_points = [item.strip() for item in params.get("focusPoints", []) if str(item).strip()]
    entry = _match_entry(knowledge_base, course_name, goals, focus_points)
    if not focus_points:
        focus_points = entry["key_points"][:2]
    difficult_points = entry.get("difficult_points", focus_points[:1]) or focus_points[:1]

    stage_map = {
        "THEORY": (
            ["课程导入", "新知讲授", "案例分析", "课堂练习", "总结提升"],
            [10, 35, 20, 20, 15],
            ["情境导入", "讲授与板书", "案例拆解", "练习反馈", "归纳与作业布置"],
        ),
        "PRACTICE": (
            ["安全提示", "原理说明", "教师演示", "分组实训", "结果分析", "总结考核"],
            [10, 15, 20, 30, 15, 10],
            ["设备检查", "讲授与演示", "操作演示", "分组实操", "误差分析", "结果评价"],
        ),
        "TRAINING": (
            ["场景导入", "规范要点", "工程案例", "岗位演练", "复盘答疑"],
            [15, 20, 30, 20, 15],
            ["任务驱动", "规范解读", "案例研讨", "岗位演练", "总结与答疑"],
        ),
        "REVIEW": (
            ["知识梳理", "重点辨析", "典型题训练", "错题回顾", "课堂总结"],
            [15, 20, 30, 20, 15],
            ["导图梳理", "难点拆分", "分层训练", "错题讲评", "总结提升"],
        ),
    }
    stages, weights, methods = stage_map.get(template_type, stage_map["THEORY"])
    durations = _apportion_minutes(hours * 45, weights)

    outline = []
    concepts = entry["concepts"]
    for idx, stage_name in enumerate(stages):
        start = idx % max(1, len(concepts))
        knowledge_items = concepts[start : start + 2]
        if len(knowledge_items) < 2:
            knowledge_items += concepts[: 2 - len(knowledge_items)]
        outline.append(
            {
                "title": stage_name,
                "duration": _format_duration(durations[idx]),
                "content": knowledge_items[0],
                "method": methods[idx],
                "knowledge_points": knowledge_items,
            }
        )

    return {
        "course_name": course_name,
        "template_name": template_meta.get("template_name") or template_meta.get("templateName"),
        "course_type": template_type,
        "course_type_label": COURSE_TYPE_LABELS.get(template_type, template_type),
        "hours": hours,
        "audience": audience,
        "generated_at": params.get("generatedAt", ""),
        "goals": goals,
        "focus_points": focus_points,
        "difficult_points": difficult_points,
        "cases": entry["cases"][:3],
        "exercises": entry["exercises"][:3],
        "homework": entry.get("homework", ["根据课堂内容完善学习笔记。"]),
        "summary": entry.get("summary", "围绕核心概念完成知识回顾，并结合实际工程场景进行迁移。"),
        "outline": outline,
        "resources": entry.get("resources", []),
        "formulas": entry.get("formulas", []),
        "generated_at": params.get("generatedAt", ""),
    }


def build_plan_template_context(plan):
    context = dict(plan)
    context["goals_text"] = "\n".join([f"- {item}" for item in plan["goals"]])
    context["focus_points_text"] = "；".join(plan["focus_points"])
    context["difficult_points_text"] = "；".join(plan["difficult_points"])
    context["cases_text"] = "\n".join([f"- {item}" for item in plan["cases"]])
    context["exercises_text"] = "\n".join([f"- {item}" for item in plan["exercises"]])
    context["homework_text"] = "\n".join([f"- {item}" for item in plan["homework"]])
    context["outline_text"] = "\n".join(
        [
            f"{idx + 1}. {item['title']}（{item['duration']}）- {item['content']}"
            for idx, item in enumerate(plan["outline"])
        ]
    )
    context["outline_detail_text"] = "\n\n".join(
        [
            "\n".join(
                [
                    f"{idx + 1}. {item['title']}（{item['duration']}）",
                    f"教学内容：{item['content']}",
                    f"教学方法：{item['method']}",
                    f"知识点：{'；'.join(item['knowledge_points'])}",
                ]
            )
            for idx, item in enumerate(plan["outline"])
        ]
    )
    context.update(
        {
            "课程名称": plan["course_name"],
            "模板名称": plan["template_name"],
            "课程类型": plan["course_type_label"],
            "授课对象": plan["audience"],
            "总课时": f"{plan['hours']} 课时",
            "生成时间": plan.get("generated_at", ""),
            "教学目标": context["goals_text"],
            "教学重点": context["focus_points_text"],
            "教学难点": context["difficult_points_text"],
            "教学案例": context["cases_text"],
            "课堂练习": context["exercises_text"],
            "课后任务": context["homework_text"],
            "教学总结": plan["summary"],
            "教学流程": context["outline_detail_text"],
        }
    )
    for index, item in enumerate(plan["outline"], start=1):
        context[f"outline_{index}_title"] = item["title"]
        context[f"outline_{index}_duration"] = item["duration"]
        context[f"outline_{index}_content"] = item["content"]
        context[f"outline_{index}_method"] = item["method"]
        context[f"outline_{index}_knowledge_points"] = "；".join(item["knowledge_points"])
        context[f"环节{index}标题"] = item["title"]
        context[f"环节{index}时长"] = item["duration"]
        context[f"环节{index}内容"] = item["content"]
        context[f"环节{index}方法"] = item["method"]
        context[f"环节{index}知识点"] = "；".join(item["knowledge_points"])
    return context


def render_plan_markdown(plan, template_text):
    body = template_text or DEFAULT_PLAN_TEMPLATE
    return Template(body).render(**build_plan_template_context(plan)).strip() + "\n"


def render_plan_html(plan):
    sections = []
    for item in plan["outline"]:
        sections.append(
            f"""
            <section class="card">
              <h3>{html.escape(item['title'])}</h3>
              <p><strong>时长：</strong>{html.escape(item['duration'])}</p>
              <p><strong>教学内容：</strong>{html.escape(item['content'])}</p>
              <p><strong>教学方法：</strong>{html.escape(item['method'])}</p>
              <p><strong>知识点：</strong>{html.escape('；'.join(item['knowledge_points']))}</p>
            </section>
            """
        )

    goals = "".join([f"<li>{html.escape(goal)}</li>" for goal in plan["goals"]])
    cases = "".join([f"<li>{html.escape(item)}</li>" for item in plan["cases"]])
    exercises = "".join([f"<li>{html.escape(item)}</li>" for item in plan["exercises"]])
    homework = "".join([f"<li>{html.escape(item)}</li>" for item in plan["homework"]])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(plan['course_name'])}教学方案</title>
  <style>
    body {{
      margin: 0;
      padding: 32px;
      font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
      background: linear-gradient(135deg, #eef5f9 0%, #ffffff 55%, #f8f4ec 100%);
      color: #153047;
    }}
    .sheet {{
      max-width: 980px;
      margin: 0 auto;
      background: rgba(255, 255, 255, 0.92);
      border-radius: 24px;
      padding: 32px;
      box-shadow: 0 20px 40px rgba(21, 48, 71, 0.12);
    }}
    h1, h2 {{ margin-top: 0; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
    }}
    .card {{
      background: #f5fbff;
      border: 1px solid #d5e6ef;
      border-radius: 16px;
      padding: 18px;
      margin-bottom: 16px;
    }}
  </style>
</head>
<body>
  <main class="sheet">
    <h1>{html.escape(plan['course_name'])}教学方案</h1>
    <p>模板：{html.escape(plan['template_name'])} ｜ 课程类型：{html.escape(plan['course_type_label'])} ｜ 授课对象：{html.escape(plan['audience'])} ｜ 总课时：{plan['hours']} 课时</p>
    <h2>教学目标</h2>
    <ul>{goals}</ul>
    <h2>教学重难点</h2>
    <div class="grid">
      <div class="card"><strong>重点</strong><p>{html.escape('；'.join(plan['focus_points']))}</p></div>
      <div class="card"><strong>难点</strong><p>{html.escape('；'.join(plan['difficult_points']))}</p></div>
    </div>
    <h2>教学流程</h2>
    {''.join(sections)}
    <h2>案例资源</h2>
    <ul>{cases}</ul>
    <h2>课堂练习</h2>
    <ul>{exercises}</ul>
    <h2>课后任务</h2>
    <ul>{homework}</ul>
    <h2>教学总结</h2>
    <p>{html.escape(plan['summary'])}</p>
  </main>
</body>
</html>
"""


def teaching_plan_lines(plan):
    lines = [
        f"{plan['course_name']}教学方案",
        "",
        f"模板：{plan['template_name']}",
        f"课程类型：{plan['course_type_label']}",
        f"授课对象：{plan['audience']}",
        f"总课时：{plan['hours']}课时",
        "",
        "教学目标：",
    ]
    lines.extend([f"{idx + 1}. {goal}" for idx, goal in enumerate(plan["goals"])])
    lines.append("")
    lines.append(f"教学重点：{'；'.join(plan['focus_points'])}")
    lines.append(f"教学难点：{'；'.join(plan['difficult_points'])}")
    lines.append("")
    lines.append("教学流程：")
    for idx, item in enumerate(plan["outline"], start=1):
        lines.append(f"{idx}. {item['title']}（{item['duration']}）")
        lines.append(f"   教学内容：{item['content']}")
        lines.append(f"   教学方法：{item['method']}")
        lines.append(f"   知识点：{'；'.join(item['knowledge_points'])}")
    lines.append("")
    lines.append("课堂练习：")
    lines.extend([f"- {item}" for item in plan["exercises"]])
    lines.append("")
    lines.append("课后任务：")
    lines.extend([f"- {item}" for item in plan["homework"]])
    lines.append("")
    lines.append("教学总结：")
    lines.append(plan["summary"])
    return lines


def build_courseware(plan, template_meta, resource_items):
    resource_names = [res["resource_name"] for res in resource_items]
    slides = [
        {
            "title": plan["course_name"],
            "bullets": [
                f"模板：{template_meta.get('template_name') or template_meta.get('templateName')}",
                f"授课对象：{plan['audience']}",
                f"总课时：{plan['hours']} 课时",
                f"课程类型：{plan['course_type_label']}",
            ],
        },
        {
            "title": "教学目标",
            "bullets": plan["goals"],
        },
        {
            "title": "教学重难点",
            "bullets": [
                f"重点：{'；'.join(plan['focus_points'])}",
                f"难点：{'；'.join(plan['difficult_points'])}",
            ],
        },
    ]

    for item in plan["outline"]:
        slides.append(
            {
                "title": f"{item['title']}（{item['duration']}）",
                "bullets": [
                    f"教学内容：{item['content']}",
                    f"教学方法：{item['method']}",
                    f"知识点：{'；'.join(item['knowledge_points'])}",
                ],
            }
        )

    slides.append({"title": "案例与资源", "bullets": plan["cases"] + resource_names})
    slides.append({"title": "课堂练习", "bullets": plan["exercises"]})
    slides.append({"title": "总结与作业", "bullets": [plan["summary"]] + plan["homework"]})

    return {
        "course_name": plan["course_name"],
        "theme_name": template_meta.get("template_name") or template_meta.get("templateName"),
        "template_name": template_meta.get("template_name") or template_meta.get("templateName"),
        "audience": plan["audience"],
        "hours": plan["hours"],
        "course_type_label": plan["course_type_label"],
        "summary": plan["summary"],
        "resource_names": resource_names,
        "slide_count": len(slides),
        "slides": slides,
    }


def build_courseware_template_context(courseware):
    context = dict(courseware)
    context["slides_text"] = "\n\n".join(
        [
            "\n".join(
                [f"Slide {index}: {slide['title']}"] + [f"- {item}" for item in slide["bullets"] if item]
            )
            for index, slide in enumerate(courseware["slides"], start=1)
        ]
    )
    context["slide_titles_text"] = "\n".join(
        [f"Slide {index}: {slide['title']}" for index, slide in enumerate(courseware["slides"], start=1)]
    )
    context["resource_names_text"] = "\n".join(courseware.get("resource_names", []))
    context.update(
        {
            "课程名称": courseware["course_name"],
            "课件主题": courseware.get("theme_name", ""),
            "模板名称": courseware.get("template_name", ""),
            "授课对象": courseware.get("audience", ""),
            "总课时": f"{courseware.get('hours', '')} 课时" if courseware.get("hours") else "",
            "课程类型": courseware.get("course_type_label", ""),
            "页数": str(courseware["slide_count"]),
            "课件摘要": courseware["slides_text"],
            "资源列表": context["resource_names_text"],
            "课程总结": courseware.get("summary", ""),
        }
    )
    for index, slide in enumerate(courseware["slides"], start=1):
        bullets_text = "\n".join([f"- {item}" for item in slide["bullets"] if item])
        plain_bullets_text = "\n".join([item for item in slide["bullets"] if item])
        context[f"slide_{index}_title"] = slide["title"]
        context[f"slide_{index}_bullets"] = bullets_text
        context[f"slide_{index}_bullets_text"] = plain_bullets_text
        context[f"第{index}页标题"] = slide["title"]
        context[f"第{index}页要点"] = bullets_text
        for bullet_index, bullet in enumerate(slide["bullets"], start=1):
            context[f"slide_{index}_bullet_{bullet_index}"] = bullet
            context[f"第{index}页第{bullet_index}条"] = bullet
    return context


def render_courseware_html(courseware):
    slide_blocks = []
    for index, slide in enumerate(courseware["slides"], start=1):
        bullets = "".join([f"<li>{html.escape(item)}</li>" for item in slide["bullets"] if item])
        slide_blocks.append(
            f"""
            <section class="slide">
              <header>
                <span class="badge">Slide {index}</span>
                <h2>{html.escape(slide['title'])}</h2>
              </header>
              <ul>{bullets}</ul>
            </section>
            """
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(courseware['course_name'])}课件预览</title>
  <style>
    body {{
      margin: 0;
      padding: 24px;
      font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(31, 96, 135, 0.18), transparent 34%),
        linear-gradient(135deg, #f8faf5 0%, #eef4fa 50%, #fdfbf4 100%);
      color: #19344c;
    }}
    .deck {{
      max-width: 1080px;
      margin: 0 auto;
      display: grid;
      gap: 18px;
    }}
    .slide {{
      min-height: 280px;
      padding: 28px;
      border-radius: 24px;
      background: rgba(255, 255, 255, 0.92);
      box-shadow: 0 18px 30px rgba(25, 52, 76, 0.12);
      border: 1px solid rgba(115, 149, 173, 0.18);
    }}
    .badge {{
      display: inline-block;
      padding: 6px 12px;
      border-radius: 999px;
      background: #dbeaf4;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    h1, h2 {{ margin: 12px 0; }}
  </style>
</head>
<body>
  <main class="deck">
    <h1>{html.escape(courseware['course_name'])}课件预览</h1>
    {''.join(slide_blocks)}
  </main>
</body>
</html>
"""


def courseware_lines(courseware):
    lines = [f"{courseware['course_name']}课件提纲", ""]
    for index, slide in enumerate(courseware["slides"], start=1):
        lines.append(f"Slide {index}: {slide['title']}")
        for bullet in slide["bullets"]:
            lines.append(f"- {bullet}")
        lines.append("")
    return lines


def validate_plan(plan, rules):
    issues = []
    required_sections = rules.get("required_sections", ["教学目标", "教学流程", "教学总结"])
    if len(plan["goals"]) < 2:
        issues.append(
            {
                "issueCode": "PLAN_GOAL_COUNT",
                "fieldPath": "goals",
                "severity": "MEDIUM",
                "message": "教学目标少于 2 项，建议补充可衡量目标。",
                "suggestion": "增加知识、能力或素养层面的目标描述。",
            }
        )
    if not plan["outline"]:
        issues.append(
            {
                "issueCode": "PLAN_OUTLINE_EMPTY",
                "fieldPath": "outline",
                "severity": "HIGH",
                "message": "教学流程为空，无法形成完整教学方案。",
                "suggestion": "至少补充导入、新授、练习、总结等环节。",
            }
        )
    for item in plan["outline"]:
        if not item["duration"]:
            issues.append(
                {
                    "issueCode": "PLAN_DURATION_MISSING",
                    "fieldPath": f"outline.{item['title']}",
                    "severity": "MEDIUM",
                    "message": f"{item['title']}缺少时长分配。",
                    "suggestion": "为每个教学环节配置明确时长。",
                }
            )
    if "教学总结" in required_sections and not plan["summary"]:
        issues.append(
            {
                "issueCode": "PLAN_SUMMARY_EMPTY",
                "fieldPath": "summary",
                "severity": "LOW",
                "message": "教学总结为空。",
                "suggestion": "补充课程回顾与学习迁移建议。",
            }
        )
    score = max(0, 100 - sum({"LOW": 5, "MEDIUM": 10, "HIGH": 20}[item["severity"]] for item in issues))
    return {
        "issues": issues,
        "score": score,
        "status": "PASS" if not issues else "WARN" if score >= 80 else "FAIL",
    }


def validate_courseware(courseware, rules):
    issues = []
    max_bullets = int(rules.get("max_bullets_per_slide", 6))
    if courseware["slide_count"] < 5:
        issues.append(
            {
                "issueCode": "CW_SLIDE_COUNT_LOW",
                "fieldPath": "slides",
                "severity": "MEDIUM",
                "message": "课件页数偏少，可能不足以支撑完整教学活动。",
                "suggestion": "增加案例、练习或总结页。",
            }
        )
    for index, slide in enumerate(courseware["slides"], start=1):
        if not slide["title"]:
            issues.append(
                {
                    "issueCode": "CW_TITLE_EMPTY",
                    "fieldPath": f"slides.{index}.title",
                    "severity": "HIGH",
                    "message": f"第 {index} 页缺少标题。",
                    "suggestion": "为每一页补充清晰标题。",
                }
            )
        if len(slide["bullets"]) > max_bullets:
            issues.append(
                {
                    "issueCode": "CW_BULLET_TOO_MANY",
                    "fieldPath": f"slides.{index}.bullets",
                    "severity": "LOW",
                    "message": f"第 {index} 页要点超过 {max_bullets} 条，阅读压力较大。",
                    "suggestion": "拆分页内容或精简文字。",
                }
            )
    score = max(0, 100 - sum({"LOW": 5, "MEDIUM": 10, "HIGH": 20}[item["severity"]] for item in issues))
    return {
        "issues": issues,
        "score": score,
        "status": "PASS" if not issues else "WARN" if score >= 80 else "FAIL",
    }


def build_docx(path, paragraphs, title="教学资料"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    created = "2026-05-11T00:00:00Z"

    def paragraph_xml(text):
        return (
            "<w:p><w:r><w:rPr><w:rFonts w:ascii=\"Calibri\" w:hAnsi=\"Calibri\" w:eastAsia=\"宋体\"/>"
            "<w:sz w:val=\"24\"/></w:rPr><w:t xml:space=\"preserve\">"
            f"{xml_escape(text)}"
            "</w:t></w:r></w:p>"
        )

    body_xml = "".join([paragraph_xml(line or " ") for line in paragraphs])
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
 xmlns:v="urn:schemas-microsoft-com:vml"
 xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:w10="urn:schemas-microsoft-com:office:word"
 xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
 xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
 xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk"
 xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml"
 xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
 mc:Ignorable="w14 wp14">
  <w:body>
    {body_xml}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"""

    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
  </w:style>
</w:styles>
"""
    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""
    rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""
    core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{xml_escape(title)}</dc:title>
  <dc:creator>Water Teaching Backend</dc:creator>
  <cp:lastModifiedBy>Water Teaching Backend</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>
"""
    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Water Teaching Backend</Application>
</Properties>
"""

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", styles_xml)
    return path
