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


# ── Exam Paper Generation ──────────────────────────────────────────

DEFAULT_EXAM_CONFIG = {
    "single_choice": {"count": 10, "score_per_question": 2},
    "true_false": {"count": 10, "score_per_question": 1},
    "fill_blank": {"count": 5, "score_per_question": 2},
    "short_answer": {"count": 3, "score_per_question": 10},
    "essay": {"count": 1, "score_per_question": 30},
}

_CHOICE_PREFIX = ["A", "B", "C", "D", "E", "F"]

_OPPOSITE_TERMS = [
    ("补给", "排泄"),
    ("含水层", "隔水层"),
    ("承压水", "潜水"),
    ("上游", "下游"),
    ("坝体", "闸门"),
    ("明渠", "暗管"),
    ("灌溉", "排水"),
    ("入渗", "蒸发"),
    ("理论课", "实训课"),
    ("平面图", "剖面图"),
]


def _term_mask(text):
    """从文本中提取一个关键术语作为填空答案，返回(挖空后的文本, 答案)。"""
    import re
    separators = ["与", "和", "、", "的", "对", "在", "是", "等", "及"]
    for sep in separators:
        if sep in text:
            parts = text.split(sep, 1)
            if len(parts[0]) >= 2 and len(parts[0]) <= 10:
                masked = "______" + sep + parts[1]
                return masked, parts[0]
    if len(text) >= 4:
        half = len(text) // 2
        return text[:half] + "______", text[half : half + 6].rstrip("。；，,")
    return "______" + text, text[:6]


def _generate_wrong_statement(concept_text):
    """对一条知识点做错误转换，返回(错误表述, 被改的词, 替代词)。"""
    import re
    for wrong, right in _OPPOSITE_TERMS:
        if wrong in concept_text:
            return concept_text.replace(wrong, right), wrong, right
        if right in concept_text:
            return concept_text.replace(right, wrong), right, wrong
    words = re.findall(r"[一-鿿]{2,4}", concept_text)
    if len(words) >= 2:
        idx = len(words) // 2
        swapped = list(words)
        swapped[idx] = "相关理论"
        return "".join(swapped), words[idx], "相关理论"
    return concept_text + "（错误）", "", ""


def _build_single_choice_questions(concepts, count, score_per):
    """从知识点列表生成单选题。"""
    questions = []
    pool = [c for c in concepts if len(c) >= 6]
    if len(pool) < 2:
        return questions
    used = min(count, len(pool))
    for i in range(used):
        correct = pool[i]
        others = [c for j, c in enumerate(pool) if j != i]
        distractors = []
        for d in others[:3]:
            if len(d) > len(correct):
                distractors.append(d[: len(correct) - 2] + "……")
            elif len(d) < len(correct) - 3:
                distractors.append(d + "等相关内容。")
            else:
                distractors.append(d)
        while len(distractors) < 3:
            distractors.append("以上说法均不准确。")
        options_texts = [correct] + distractors[:3]
        shuffled_indices = list(range(4))
        import random as _random
        _random.shuffle(shuffled_indices)
        options = [
            f"{_CHOICE_PREFIX[idx]}. {options_texts[orig]}"
            for idx, orig in enumerate(shuffled_indices)
        ]
        answer_letter = _CHOICE_PREFIX[shuffled_indices.index(0)]
        questions.append(
            {
                "type": "SINGLE_CHOICE",
                "number": 0,
                "stem": f"以下关于{concepts[i][:12]}的描述，正确的是？",
                "options": options,
                "answer": answer_letter,
                "score": score_per,
                "knowledge_point": concepts[i],
            }
        )
    return questions


def _build_true_false_questions(concepts, count, score_per):
    """从知识点列表生成判断题。"""
    import random as _random
    questions = []
    pool = [c for c in concepts if len(c) >= 4]
    if not pool:
        return questions
    used = min(count, len(pool))
    chosen = _random.sample(pool, used) if used <= len(pool) else pool[:used]
    for i, concept in enumerate(chosen):
        is_true = _random.random() < 0.5
        if is_true:
            stem = f"{concept}。"
            answer = True
        else:
            stem, _, _ = _generate_wrong_statement(concept)
            if stem == concept or stem == f"{concept}（错误）":
                stem = f"{concept}这一说法在工程实践中并非绝对成立。"
            answer = False
        questions.append(
            {
                "type": "TRUE_FALSE",
                "number": 0,
                "stem": stem,
                "answer": answer,
                "score": score_per,
                "knowledge_point": concept,
            }
        )
    return questions


def _build_fill_blank_questions(points, count, score_per):
    """从重点/难点列表生成填空题。"""
    questions = []
    pool = [p for p in points if len(p) >= 4]
    used = min(count, len(pool))
    for i in range(used):
        stem, answer = _term_mask(pool[i])
        questions.append(
            {
                "type": "FILL_BLANK",
                "number": 0,
                "stem": stem,
                "answer": answer,
                "score": score_per,
                "knowledge_point": pool[i],
            }
        )
    return questions


def _build_short_answer_questions(focus_points, difficult_points, count, score_per):
    """从重点/难点列表生成简答题。"""
    questions = []
    pool = []
    for p in focus_points:
        if p not in pool:
            pool.append(p)
    for p in difficult_points:
        if p not in pool:
            pool.append(p)
    used = min(count, len(pool))
    for i in range(used):
        questions.append(
            {
                "type": "SHORT_ANSWER",
                "number": 0,
                "stem": f"请简述{pool[i]}。",
                "reference_answer": f"请参考教材中关于{pool[i]}的详细阐述，从概念定义、核心特征和工程应用三个方面作答。",
                "score": score_per,
                "knowledge_point": pool[i],
            }
        )
    return questions


def _build_essay_question(plan, score):
    """从公式和案例生成论述/计算题。"""
    formulas = plan.get("formulas") or []
    cases = plan.get("cases") or []
    course_name = plan.get("course_name", "本课程")

    formula_text = formulas[0] if formulas else ""
    case_text = cases[0] if cases else f"结合{plan.get('course_name', '水利工程')}领域的实际场景"

    if formula_text and case_text:
        stem = (
            f"{case_text}\n"
            f"相关知识公式：{formula_text}\n"
            f"请：(1) 解释该公式各参数的物理意义；"
            f"(2) 结合案例说明该公式在工程中的应用；"
            f"(3) 提出至少两条优化建议。"
        )
        reference = (
            f"（1）公式参数说明：{formula_text}中各参数含义请参考教材。\n"
            f"（2）工程应用：{case_text}\n"
            f"（3）优化建议：结合实际工程条件，从参数选取和边界条件两个方面提出改进措施。"
        )
    elif case_text:
        stem = (
            f"{case_text}\n"
            f"请：(1) 分析案例中涉及的核心工程技术问题；"
            f"(2) 提出系统的解决方案；"
            f"(3) 评价方案的可行性与局限性。"
        )
        reference = f"（1）核心问题分析：{case_text}\n（2）解决方案：综合运用{course_name}所学知识。\n（3）可行性评价：结合工程实际进行评判。"
    else:
        stem = (
            f"请结合{course_name}课程所学内容，完成以下论述：\n"
            f"(1) 梳理本课程的核心知识体系；\n"
            f"(2) 选取一个水利工程典型案例进行分析；\n"
            f"(3) 阐述理论知识如何指导工程实践。"
        )
        reference = "请根据课堂讲授内容和教材进行综合论述，要求逻辑清晰、论据充分。"

    return {
        "type": "ESSAY",
        "number": 0,
        "stem": stem,
        "reference_answer": reference,
        "score": score,
        "knowledge_point": plan.get("focus_points", ["课程综合应用"])[0] if plan.get("focus_points") else "课程综合应用",
        "formula": formula_text,
    }


def build_exam_paper(plan, config=None):
    """根据教学方案生成试卷。

    config 格式：
      {"single_choice": {"count": 10, "score_per_question": 2}, ...}
    传入 None 使用默认配置。
    """
    cfg = config or DEFAULT_EXAM_CONFIG

    concepts = plan.get("concepts") or []
    all_concepts = list(concepts)
    # 如果 concepts 不足，用 outline 中的知识点补充
    for item in plan.get("outline") or []:
        for kp in item.get("knowledge_points") or []:
            if kp not in all_concepts:
                all_concepts.append(kp)

    focus_points = plan.get("focus_points") or []
    difficult_points = plan.get("difficult_points") or []
    all_points = focus_points + difficult_points
    if not all_points:
        all_points = plan.get("goals") or ["课程核心内容"]

    questions = []
    number = 0

    # 单选题
    sc_cfg = cfg.get("single_choice", {"count": 10, "score_per_question": 2})
    sc_count = min(sc_cfg["count"], len(all_concepts))
    sc_questions = _build_single_choice_questions(all_concepts, sc_count, sc_cfg["score_per_question"])
    for q in sc_questions:
        number += 1
        q["number"] = number
        questions.append(q)

    # 判断题
    tf_cfg = cfg.get("true_false", {"count": 10, "score_per_question": 1})
    tf_count = min(tf_cfg["count"], len(all_concepts))
    tf_questions = _build_true_false_questions(all_concepts, tf_count, tf_cfg["score_per_question"])
    for q in tf_questions:
        number += 1
        q["number"] = number
        questions.append(q)

    # 填空题
    fb_cfg = cfg.get("fill_blank", {"count": 5, "score_per_question": 2})
    fb_count = min(fb_cfg["count"], len(all_points))
    fb_questions = _build_fill_blank_questions(all_points, fb_count, fb_cfg["score_per_question"])
    for q in fb_questions:
        number += 1
        q["number"] = number
        questions.append(q)

    # 简答题
    sa_cfg = cfg.get("short_answer", {"count": 3, "score_per_question": 10})
    sa_count = min(sa_cfg["count"], len(all_points))
    sa_questions = _build_short_answer_questions(focus_points, difficult_points, sa_count, sa_cfg["score_per_question"])
    for q in sa_questions:
        number += 1
        q["number"] = number
        questions.append(q)

    # 论述/计算题
    es_cfg = cfg.get("essay", {"count": 1, "score_per_question": 30})
    es_count = min(es_cfg["count"], 1)
    for _ in range(es_count):
        number += 1
        q = _build_essay_question(plan, es_cfg["score_per_question"])
        q["number"] = number
        questions.append(q)

    total_score = sum(q["score"] for q in questions)

    return {
        "course_name": plan.get("course_name", ""),
        "total_score": total_score,
        "question_count": len(questions),
        "config": cfg,
        "questions": questions,
        "generated_at": plan.get("generated_at", ""),
    }


def render_exam_html(exam):
    """将试卷渲染为 HTML 预览（标准试卷排版，含答案）。"""
    q_blocks = []
    for q in exam["questions"]:
        qtype_label = {
            "SINGLE_CHOICE": "单选题",
            "TRUE_FALSE": "判断题",
            "FILL_BLANK": "填空题",
            "SHORT_ANSWER": "简答题",
            "ESSAY": "论述/计算题",
        }.get(q["type"], q["type"])

        answer_html = ""
        if q["type"] == "SINGLE_CHOICE":
            options_html = "".join([f"<div class=\"option\">{html.escape(opt)}</div>" for opt in q["options"]])
            answer_html = (
                f"<div class=\"options\">{options_html}</div>"
                f"<p class=\"answer\"><strong>参考答案：</strong>{html.escape(q['answer'])}</p>"
            )
        elif q["type"] == "TRUE_FALSE":
            answer_html = (
                f"<p class=\"answer\"><strong>参考答案：</strong>{'正确' if q['answer'] else '错误'}</p>"
            )
        elif q["type"] == "FILL_BLANK":
            answer_html = f"<p class=\"answer\"><strong>参考答案：</strong>{html.escape(q['answer'])}</p>"
        elif q["type"] == "SHORT_ANSWER":
            answer_html = (
                f"<div class=\"answer-area\">"
                f"<p><em>答题区域：</em></p>"
                f"<div class=\"answer-lines\"></div>"
                f"</div>"
                f"<p class=\"answer\"><strong>参考答案：</strong>{html.escape(q.get('reference_answer', ''))}</p>"
            )
        elif q["type"] == "ESSAY":
            answer_html = (
                f"<div class=\"answer-area\">"
                f"<p><em>答题区域：</em></p>"
                f"<div class=\"answer-lines\" style=\"min-height:200px\"></div>"
                f"</div>"
                f"<p class=\"answer\"><strong>参考答案要点：</strong>{html.escape(q.get('reference_answer', ''))}</p>"
            )

        q_blocks.append(
            f"""
            <div class="question-card">
              <div class="question-header">
                <span class="q-number">{q['number']}.</span>
                <span class="q-type-badge">{qtype_label}</span>
                <span class="q-score">（{q['score']}分）</span>
              </div>
              <div class="question-stem">{html.escape(q['stem'])}</div>
              {answer_html}
            </div>
            """
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(exam['course_name'])}考试试卷</title>
  <style>
    body {{
      margin: 0;
      padding: 32px;
      font-family: "Microsoft YaHei", "PingFang SC", "SimSun", serif;
      background: #f4f6f9;
      color: #222;
    }}
    .paper {{
      max-width: 900px;
      margin: 0 auto;
      background: #fff;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 48px 40px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    }}
    .paper-header {{
      text-align: center;
      border-bottom: 2px solid #1a3c5e;
      padding-bottom: 24px;
      margin-bottom: 32px;
    }}
    .paper-header h1 {{
      font-size: 22px;
      margin: 0 0 12px;
      letter-spacing: 0.1em;
    }}
    .paper-meta {{
      display: flex;
      justify-content: center;
      gap: 32px;
      font-size: 14px;
      color: #555;
    }}
    .question-card {{
      border: 1px solid #e8ecf1;
      border-radius: 8px;
      padding: 18px 22px;
      margin-bottom: 16px;
      background: #fafbfc;
    }}
    .question-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }}
    .q-number {{
      font-weight: 700;
      font-size: 16px;
      color: #1a3c5e;
    }}
    .q-type-badge {{
      font-size: 12px;
      padding: 2px 10px;
      border-radius: 12px;
      background: #e0ecf4;
      color: #2a5078;
    }}
    .q-score {{
      font-size: 13px;
      color: #888;
      margin-left: auto;
    }}
    .question-stem {{
      font-size: 15px;
      line-height: 1.7;
      margin-bottom: 10px;
      white-space: pre-line;
    }}
    .options {{
      margin: 8px 0 8px 20px;
    }}
    .option {{
      padding: 4px 0;
      font-size: 14px;
    }}
    .answer {{
      margin-top: 8px;
      padding: 8px 12px;
      background: #e8f5e9;
      border-left: 3px solid #4caf50;
      border-radius: 4px;
      font-size: 14px;
    }}
    .answer-area {{
      margin: 8px 0;
      padding: 8px 12px;
      background: #fefefe;
      border: 1px dashed #ccc;
      border-radius: 4px;
    }}
    .answer-lines {{
      min-height: 80px;
      background: repeating-linear-gradient(
        transparent, transparent 27px, #e0e0e0 27px, #e0e0e0 28px
      );
    }}
    @media print {{
      body {{ background: #fff; padding: 0; }}
      .paper {{ box-shadow: none; border: none; }}
    }}
  </style>
</head>
<body>
  <main class="paper">
    <div class="paper-header">
      <h1>{html.escape(exam['course_name'])}考试试卷</h1>
      <div class="paper-meta">
        <span>满分：{exam['total_score']}分</span>
        <span>题量：{exam['question_count']}题</span>
        <span>生成时间：{exam.get('generated_at', '')}</span>
      </div>
    </div>
    {''.join(q_blocks)}
  </main>
</body>
</html>
"""


def render_exam_markdown(exam, with_answers=True):
    """将试卷渲染为 Markdown（教师版含答案）。"""
    lines = [
        f"# {exam['course_name']}考试试卷",
        "",
        f"- 满分：{exam['total_score']}分",
        f"- 题量：{exam['question_count']}题",
        f"- 生成时间：{exam.get('generated_at', '')}",
        "",
        "---",
        "",
    ]

    current_type = None
    type_headers = {
        "SINGLE_CHOICE": "## 一、单选题",
        "TRUE_FALSE": "## 二、判断题",
        "FILL_BLANK": "## 三、填空题",
        "SHORT_ANSWER": "## 四、简答题",
        "ESSAY": "## 五、论述/计算题",
    }

    for q in exam["questions"]:
        if q["type"] != current_type:
            current_type = q["type"]
            lines.append(type_headers.get(current_type, f"## {current_type}"))
            lines.append("")

        lines.append(f"**{q['number']}.（{q['score']}分）** {q['stem']}")

        if q["type"] == "SINGLE_CHOICE":
            for opt in q["options"]:
                lines.append(f"  - {opt}")
            if with_answers:
                lines.append(f"  > 参考答案：**{q['answer']}**")
        elif q["type"] == "TRUE_FALSE":
            if with_answers:
                answer_text = "正确" if q["answer"] else "错误"
                lines.append(f"  > 参考答案：**{answer_text}**")
        elif q["type"] == "FILL_BLANK":
            if with_answers:
                lines.append(f"  > 参考答案：**{q['answer']}**")
        elif q["type"] == "SHORT_ANSWER":
            lines.append("")
            if with_answers:
                lines.append(f"  > 参考答案：{q.get('reference_answer', '')}")
        elif q["type"] == "ESSAY":
            lines.append("")
            if with_answers:
                lines.append(f"  > 参考答案要点：{q.get('reference_answer', '')}")

        lines.append("")

    return "\n".join(lines) + "\n"


def render_exam_student_markdown(exam):
    """将试卷渲染为 Markdown（学生版不含答案）。"""
    return render_exam_markdown(exam, with_answers=False)


def exam_lines(exam):
    """试卷文本行形式。"""
    lines = [
        f"{exam['course_name']}考试试卷",
        f"满分：{exam['total_score']}分 | 题量：{exam['question_count']}题",
        "",
    ]
    for q in exam["questions"]:
        lines.append(f"{q['number']}. [{q['type']}]（{q['score']}分）{q['stem']}")
        if q["type"] == "SINGLE_CHOICE":
            for opt in q["options"]:
                lines.append(f"    {opt}")
            lines.append(f"    答案：{q['answer']}")
        elif q["type"] in ("TRUE_FALSE", "FILL_BLANK"):
            lines.append(f"    答案：{q['answer']}")
        elif q["type"] in ("SHORT_ANSWER", "ESSAY"):
            lines.append(f"    参考答案：{q.get('reference_answer', '')[:80]}……")
        lines.append("")
    return lines


def validate_exam(exam, rules=None):
    """校验试卷质量。"""
    issues = []
    cfg = exam.get("config") or DEFAULT_EXAM_CONFIG

    # 检查各题型数量
    for qtype, expected in cfg.items():
        actual = sum(1 for q in exam["questions"] if q["type"] == qtype.upper())
        if actual < expected.get("count", 0):
            issues.append(
                {
                    "issueCode": f"EXAM_{qtype.upper()}_COUNT",
                    "fieldPath": "questions",
                    "severity": "MEDIUM",
                    "message": f"{qtype}数量不足：期望{expected['count']}，实际{actual}。",
                    "suggestion": f"补充更多知识点以生成足够的{qtype}。",
                }
            )

    # 检查总分
    total = sum(q["score"] for q in exam["questions"])
    if total <= 0:
        issues.append(
            {
                "issueCode": "EXAM_SCORE_ZERO",
                "fieldPath": "total_score",
                "severity": "HIGH",
                "message": "试卷总分为零，无法使用。",
                "suggestion": "检查试题生成逻辑。",
            }
        )

    # 检查是否有题目
    if not exam.get("questions"):
        issues.append(
            {
                "issueCode": "EXAM_EMPTY",
                "fieldPath": "questions",
                "severity": "HIGH",
                "message": "试卷无任何题目。",
                "suggestion": "确保教学方案包含足够的知识点和重点内容。",
            }
        )

    # 检查是否有空答案
    for q in exam["questions"]:
        answer = q.get("answer") or q.get("reference_answer", "")
        if not answer or not str(answer).strip():
            issues.append(
                {
                    "issueCode": "EXAM_ANSWER_MISSING",
                    "fieldPath": f"questions.{q['number']}",
                    "severity": "HIGH",
                    "message": f"第{q['number']}题缺少答案。",
                    "suggestion": "为该题目补充参考答案。",
                }
            )

    score = max(0, 100 - sum({"LOW": 5, "MEDIUM": 10, "HIGH": 20}[item["severity"]] for item in issues))
    return {
        "issues": issues,
        "score": score,
        "status": "PASS" if not issues else "WARN" if score >= 80 else "FAIL",
    }
