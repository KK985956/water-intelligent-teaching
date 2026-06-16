import io
import importlib
import json
import os
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from pathlib import Path

from backend.app import create_app
from backend.app.database import execute
from backend.app.office import slides_to_pptx
from backend.app.services import seed_defaults


class BackendFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.app = create_app(
            {
                "TESTING": True,
                "SYNC_TASKS": True,
                "START_WORKER": False,
                "STORAGE_DIR": root / "storage",
                "TEMPLATE_DIR": root / "storage" / "templates",
                "GENERATED_DIR": root / "storage" / "generated",
                "EXPORT_DIR": root / "storage" / "exports",
                "RESOURCE_DIR": root / "storage" / "resources",
                "DATABASE_PATH": root / "storage" / "test.db",
                "SECRET_KEY": "unit-test-secret",
            }
        )
        self.client = self.app.test_client()
        self.token = self.login()["token"]

    def tearDown(self):
        self.temp_dir.cleanup()

    def auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def count_pptx_slides(self, file_path):
        with zipfile.ZipFile(file_path) as archive:
            root = ET.fromstring(archive.read("docProps/app.xml"))
            namespace = {"ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"}
            slides = root.find("ep:Slides", namespace)
            return int(slides.text) if slides is not None and slides.text else 0

    def extract_pptx_text(self, file_path):
        texts = []
        with zipfile.ZipFile(file_path) as archive:
            for name in archive.namelist():
                if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                    root = ET.fromstring(archive.read(name))
                    for node in root.iter():
                        if node.text and node.tag.endswith("}t"):
                            texts.append(node.text)
        return "\n".join(texts)

    def login(self, username="teacher", password="teacher123"):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password, "captcha": "2026"},
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["data"]

    def test_openai_config_defaults_keep_local_courseware_available(self):
        self.app.config["OPENAI_API_KEY"] = ""
        self.app.config["AI_COURSEWARE_ENABLED"] = False
        self.app.config["OPENAI_IMAGE_ENABLED"] = False

        templates = self.client.get("/api/v1/templates", headers=self.auth_headers())
        template_list = templates.get_json()["data"]["list"]
        plan_template = next(item for item in template_list if item["templateType"] == "THEORY")
        courseware_template = next(item for item in template_list if item["templateType"] == "TRAINING")

        create_plan = self.client.post(
            "/api/v1/generation/plans",
            headers=self.auth_headers(),
            json={
                "templateId": plan_template["templateId"],
                "courseName": "水文地质学",
                "hours": 16,
                "audience": "本科二年级",
                "goals": ["掌握基本概念", "理解地下水运动规律"],
                "focusPoints": ["地下水补给与排泄", "含水层特征"],
            },
        )
        self.assertEqual(create_plan.status_code, 200)
        plan_id = create_plan.get_json()["data"]["result"]["targetId"]

        create_courseware = self.client.post(
            "/api/v1/generation/coursewares",
            headers=self.auth_headers(),
            json={
                "planId": plan_id,
                "coursewareTemplateId": courseware_template["templateId"],
                "resources": [],
            },
        )
        self.assertEqual(create_courseware.status_code, 200)
        self.assertGreater(create_courseware.get_json()["data"]["result"]["slideCount"], 1)

    def sample_plan(self):
        return {
            "course_name": "水文地质学",
            "template_name": "标准化课件模板",
            "course_type": "THEORY",
            "course_type_label": "理论课",
            "hours": 16,
            "audience": "本科二年级",
            "goals": ["掌握地下水基本概念", "理解地下水补给与排泄过程"],
            "focus_points": ["地下水补给", "地下水排泄"],
            "difficult_points": ["含水层参数识别"],
            "cases": ["某灌区地下水位变化案例"],
            "exercises": ["绘制地下水补给路径示意图"],
            "homework": ["完成案例分析报告"],
            "summary": "围绕地下水运动过程建立工程分析思路。",
            "outline": [
                {
                    "title": "课程导入",
                    "duration": "15分钟",
                    "content": "地下水与水利工程的关系",
                    "method": "情境导入",
                    "knowledge_points": ["地下水", "水循环"],
                },
                {
                    "title": "案例分析",
                    "duration": "30分钟",
                    "content": "灌区地下水位变化",
                    "method": "案例讨论",
                    "knowledge_points": ["补给", "排泄"],
                },
            ],
        }

    def test_ai_courseware_disabled_without_key_returns_none(self):
        from backend.app.ai_generation import build_courseware_with_ai

        with self.app.app_context():
            self.app.config["AI_COURSEWARE_ENABLED"] = True
            self.app.config["OPENAI_API_KEY"] = ""
            result = build_courseware_with_ai(self.sample_plan(), {"templateName": "AI模板"}, [])
        self.assertIsNone(result)

    def test_openai_base_url_config_is_available(self):
        with self.app.app_context():
            self.app.config["OPENAI_BASE_URL"] = "https://example-openai-compatible.test/v1"
            self.assertEqual(self.app.config["OPENAI_BASE_URL"], "https://example-openai-compatible.test/v1")

    def test_config_loads_backend_env_file_without_committing_secret(self):
        config_module = importlib.import_module("backend.app.config")
        env_path = Path(config_module.__file__).resolve().parent.parent / ".env"
        original = env_path.read_text(encoding="utf-8") if env_path.exists() else None
        original_env = {
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
            "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL"),
            "WATER_AI_COURSEWARE_ENABLED": os.environ.get("WATER_AI_COURSEWARE_ENABLED"),
        }

        try:
            for key in original_env:
                os.environ.pop(key, None)
            env_path.write_text(
                "\n".join(
                    [
                        "OPENAI_API_KEY=env-file-test-key",
                        "OPENAI_BASE_URL=https://example.test/v1",
                        "WATER_AI_COURSEWARE_ENABLED=1",
                    ]
                ),
                encoding="utf-8",
            )
            reloaded = importlib.reload(config_module)

            self.assertEqual(reloaded.Config.OPENAI_API_KEY, "env-file-test-key")
            self.assertEqual(reloaded.Config.OPENAI_BASE_URL, "https://example.test/v1")
            self.assertTrue(reloaded.Config.AI_COURSEWARE_ENABLED)
        finally:
            if original is None:
                env_path.unlink(missing_ok=True)
            else:
                env_path.write_text(original, encoding="utf-8")
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            importlib.reload(config_module)

    def test_ai_courseware_normalizes_fake_openai_json(self):
        from backend.app.ai_generation import build_courseware_with_ai

        payload = {
            "theme_name": "AI增强课件",
            "slides": [
                {
                    "title": "地下水运动的工程意义",
                    "subtitle": "从概念到灌区案例",
                    "layout": "cover",
                    "bullets": ["连接水循环与工程调度", "建立问题意识"],
                    "image_prompt": "地下水补给过程教学示意图",
                    "speaker_notes": "引导学生观察补给路径。",
                },
                {
                    "title": "补给与排泄构成动态平衡",
                    "layout": "image_right",
                    "bullets": ["降雨入渗形成补给", "河道与蒸发形成排泄"],
                    "image_prompt": "含水层补给排泄剖面图",
                },
            ],
        }

        class FakeResponses:
            def create(self, **kwargs):
                return SimpleNamespace(output_text=json.dumps(payload, ensure_ascii=False))

        fake_client = SimpleNamespace(responses=FakeResponses())
        with self.app.app_context():
            self.app.config["AI_COURSEWARE_ENABLED"] = True
            self.app.config["OPENAI_API_KEY"] = "test-key"
            courseware = build_courseware_with_ai(
                self.sample_plan(),
                {"templateName": "AI模板", "templateType": "TRAINING"},
                [],
                client=fake_client,
            )

        self.assertIsNotNone(courseware)
        self.assertEqual(courseware["theme_name"], "AI增强课件")
        self.assertEqual(courseware["slide_count"], 2)
        self.assertEqual(courseware["slides"][0]["layout"], "cover")
        self.assertEqual(courseware["slides"][1]["image_prompt"], "含水层补给排泄剖面图")

    def test_ai_courseware_bad_json_returns_none(self):
        from backend.app.ai_generation import build_courseware_with_ai

        class FakeResponses:
            def create(self, **kwargs):
                return SimpleNamespace(output_text="{not-json")

        fake_client = SimpleNamespace(responses=FakeResponses())
        with self.app.app_context():
            self.app.config["AI_COURSEWARE_ENABLED"] = True
            self.app.config["OPENAI_API_KEY"] = "test-key"
            result = build_courseware_with_ai(self.sample_plan(), {"templateName": "AI模板"}, [], client=fake_client)

        self.assertIsNone(result)

    def test_layout_aware_pptx_includes_subtitle_and_image_prompt(self):
        output_path = Path(self.temp_dir.name) / "layout_courseware.pptx"
        slides_to_pptx(
            [
                {
                    "title": "地下水运动的工程意义",
                    "subtitle": "从水循环到灌区调度",
                    "layout": "cover",
                    "bullets": ["建立工程问题意识", "理解补给与排泄关系"],
                    "image_prompt": "地下水补给过程教学示意图",
                },
                {
                    "title": "补给与排泄构成动态平衡",
                    "layout": "image_right",
                    "bullets": ["降雨入渗形成补给", "河道排泄影响水位"],
                    "image_prompt": "含水层补给排泄剖面图",
                    "speaker_notes": "引导学生对照剖面图解释水位变化。",
                },
            ],
            output_path,
        )

        self.assertEqual(self.count_pptx_slides(output_path), 2)
        text = self.extract_pptx_text(output_path)
        self.assertIn("从水循环到灌区调度", text)
        self.assertIn("含水层补给排泄剖面图", text)
        self.assertIn("引导学生对照剖面图解释水位变化。", text)

    def test_plan_to_courseware_flow(self):
        templates = self.client.get("/api/v1/templates", headers=self.auth_headers())
        self.assertEqual(templates.status_code, 200)
        template_list = templates.get_json()["data"]["list"]
        self.assertGreaterEqual(len(template_list), 2)
        plan_template = next(item for item in template_list if item["templateType"] == "THEORY")
        courseware_template = next(item for item in template_list if item["templateType"] == "TRAINING")

        create_plan = self.client.post(
            "/api/v1/generation/plans",
            headers=self.auth_headers(),
            json={
                "templateId": plan_template["templateId"],
                "courseName": "水文地质学",
                "hours": 16,
                "audience": "本科二年级",
                "goals": ["掌握水文地质基本概念", "理解地下水运动规律"],
                "focusPoints": ["地下水补给", "地下水排泄"],
            },
        )
        self.assertEqual(create_plan.status_code, 200)
        plan_task = create_plan.get_json()["data"]
        self.assertEqual(plan_task["status"], "SUCCESS")
        plan_id = plan_task["result"]["targetId"]

        preview = self.client.get(plan_task["result"]["previewUrl"], headers=self.auth_headers())
        self.assertEqual(preview.status_code, 200)
        preview.close()

        validation = self.client.post(
            "/api/v1/validation/format",
            headers=self.auth_headers(),
            json={"targetId": plan_id, "targetType": "PLAN"},
        )
        self.assertEqual(validation.status_code, 200)

        content_response = self.client.get(f"/api/v1/content/PLAN/{plan_id}", headers=self.auth_headers())
        self.assertEqual(content_response.status_code, 200)
        content = content_response.get_json()["data"]["content"]
        content["summary"] = "人工编辑后的课堂总结"
        edit_response = self.client.patch(
            f"/api/v1/content/PLAN/{plan_id}",
            headers=self.auth_headers(),
            json={"content": content},
        )
        self.assertEqual(edit_response.status_code, 200)
        edited_preview = self.client.get(edit_response.get_json()["data"]["previewUrl"], headers=self.auth_headers())
        self.assertEqual(edited_preview.status_code, 200)
        self.assertIn("人工编辑后的课堂总结", edited_preview.get_data(as_text=True))
        edited_preview.close()

        create_courseware = self.client.post(
            "/api/v1/generation/coursewares",
            headers=self.auth_headers(),
            json={
                "planId": plan_id,
                "coursewareTemplateId": courseware_template["templateId"],
                "resources": [],
            },
        )
        self.assertEqual(create_courseware.status_code, 200)
        courseware_task = create_courseware.get_json()["data"]
        self.assertEqual(courseware_task["status"], "SUCCESS")
        courseware_id = courseware_task["result"]["targetId"]

        courseware_content = self.client.get(f"/api/v1/content/COURSEWARE/{courseware_id}", headers=self.auth_headers())
        self.assertEqual(courseware_content.status_code, 200)
        courseware_payload = courseware_content.get_json()["data"]["content"]
        courseware_payload["slides"][0]["bullets"].append("人工补充的课件要点")
        courseware_edit = self.client.patch(
            f"/api/v1/content/COURSEWARE/{courseware_id}",
            headers=self.auth_headers(),
            json={"content": courseware_payload},
        )
        self.assertEqual(courseware_edit.status_code, 200)
        courseware_preview = self.client.get(courseware_edit.get_json()["data"]["previewUrl"], headers=self.auth_headers())
        self.assertEqual(courseware_preview.status_code, 200)
        self.assertIn("人工补充的课件要点", courseware_preview.get_data(as_text=True))
        courseware_preview.close()

        export_response = self.client.post(
            "/api/v1/exports",
            headers=self.auth_headers(),
            json={"targetId": plan_id, "format": "docx", "expiryDays": 3, "shareScope": "private"},
        )
        self.assertEqual(export_response.status_code, 200)
        download_url = export_response.get_json()["data"]["downloadUrl"]
        download = self.client.get(download_url, headers=self.auth_headers())
        self.assertEqual(download.status_code, 200)
        download.close()

        export_html = self.client.post(
            "/api/v1/exports",
            headers=self.auth_headers(),
            json={"targetId": courseware_id, "format": "html", "expiryDays": 3, "shareScope": "public"},
        )
        self.assertEqual(export_html.status_code, 200)

        limited_share = self.client.post(
            "/api/v1/exports",
            headers=self.auth_headers(),
            json={"targetId": plan_id, "format": "html", "expiryDays": 3, "shareScope": "public", "maxDownloads": 1},
        )
        self.assertEqual(limited_share.status_code, 200)
        share_url = limited_share.get_json()["data"]["shareUrl"]
        first_share = self.client.get(share_url)
        self.assertEqual(first_share.status_code, 200)
        first_share.close()
        second_share = self.client.get(share_url)
        self.assertEqual(second_share.status_code, 410)

    def test_frontend_entry_and_readonly_lists(self):
        index = self.client.get("/")
        self.assertEqual(index.status_code, 200)
        index_html = index.get_data(as_text=True)
        self.assertIn("水利智能教学应用工作台", index_html)
        self.assertIn('id="template-upload-form"', index_html)
        self.assertIn('id="template-version-form"', index_html)
        index.close()

        runtime = self.client.get("/api/v1/runtime/context", headers=self.auth_headers())
        self.assertEqual(runtime.status_code, 200)
        self.assertIn("progressSocket", runtime.get_json()["data"])

        resources = self.client.get("/api/v1/resources", headers=self.auth_headers())
        self.assertEqual(resources.status_code, 200)
        self.assertIn("list", resources.get_json()["data"])

        tasks = self.client.get("/api/v1/tasks", headers=self.auth_headers())
        self.assertEqual(tasks.status_code, 200)
        self.assertIsInstance(tasks.get_json()["data"], list)

    def test_template_and_resource_upload(self):
        upload_template = self.client.post(
            "/api/v1/templates/upload",
            headers=self.auth_headers(),
            data={
                "type": "THEORY",
                "name": "自定义模板",
                "rulesJson": "{\"required_sections\":[\"教学目标\",\"教学流程\"]}",
                "file": (io.BytesIO("## {{ course_name }}".encode("utf-8")), "custom_template.md"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_template.status_code, 200)
        template_detail = upload_template.get_json()["data"]
        template_id = template_detail["templateId"]
        self.assertTrue(template_id.startswith("TPL-"))
        self.assertEqual(template_detail["templateType"], "THEORY")
        self.assertIn("course_name", template_detail["placeholders"])
        self.assertEqual(template_detail["formatRules"]["required_sections"], ["教学目标", "教学流程"])

        upload_resource = self.client.post(
            "/api/v1/resources/upload",
            headers=self.auth_headers(),
            data={
                "resourceType": "CASE",
                "tags": "地下水,案例",
                "file": (io.BytesIO("案例内容".encode("utf-8")), "case.txt"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_resource.status_code, 200)
        resource_id = upload_resource.get_json()["data"]["resourceId"]
        self.assertTrue(resource_id.startswith("RES-"))

    def test_seeded_open_source_ppt_templates_are_registered(self):
        response = self.client.get("/api/v1/templates?type=TRAINING&size=100", headers=self.auth_headers())
        self.assertEqual(response.status_code, 200)
        templates = response.get_json()["data"]["list"]
        open_source_templates = [
            item
            for item in templates
            if item["templateId"].startswith("TPL-PPT-")
        ]

        self.assertEqual(len(open_source_templates), 30)
        self.assertTrue(all(item["templateName"].startswith("Open Source PPT - ") for item in open_source_templates))
        self.assertTrue(all(item["templateType"] == "TRAINING" for item in open_source_templates))

        with self.app.app_context():
            execute("DELETE FROM t_template_version WHERE template_id = ?", ("TPL-PPT-001",))
            execute("DELETE FROM t_template WHERE template_id = ?", ("TPL-PPT-001",))
            seed_defaults()

        reseeded_response = self.client.get("/api/v1/templates?type=TRAINING&size=100", headers=self.auth_headers())
        self.assertEqual(reseeded_response.status_code, 200)
        reseeded_templates = reseeded_response.get_json()["data"]["list"]
        reseeded_open_source_templates = [
            item
            for item in reseeded_templates
            if item["templateId"].startswith("TPL-PPT-")
        ]
        self.assertEqual(len(reseeded_open_source_templates), 30)

    def test_courseware_ppt_template_expands_single_slide_template(self):
        templates = self.client.get("/api/v1/templates?type=TRAINING&size=100", headers=self.auth_headers())
        self.assertEqual(templates.status_code, 200)
        training_templates = templates.get_json()["data"]["list"]
        courseware_template = next(item for item in training_templates if item["templateId"].startswith("TPL-PPT-"))

        theory_templates = self.client.get("/api/v1/templates?type=THEORY&size=100", headers=self.auth_headers())
        plan_template = next(item for item in theory_templates.get_json()["data"]["list"] if item["templateType"] == "THEORY")

        create_plan = self.client.post(
            "/api/v1/generation/plans",
            headers=self.auth_headers(),
            json={
                "templateId": plan_template["templateId"],
                "courseName": "水文地质学",
                "hours": 16,
                "audience": "本科二年级",
                "goals": ["掌握基本概念", "理解地下水运动规律"],
                "focusPoints": ["地下水补给与排泄", "含水层特征"],
            },
        )
        self.assertEqual(create_plan.status_code, 200)
        plan_id = create_plan.get_json()["data"]["result"]["targetId"]

        create_courseware = self.client.post(
            "/api/v1/generation/coursewares",
            headers=self.auth_headers(),
            json={
                "planId": plan_id,
                "coursewareTemplateId": courseware_template["templateId"],
                "resources": [],
            },
        )
        self.assertEqual(create_courseware.status_code, 200)
        result = create_courseware.get_json()["data"]["result"]
        self.assertGreater(result["slideCount"], 1)
        pptx_path = Path(result["files"]["pptx"])
        self.assertTrue(pptx_path.exists())
        self.assertEqual(self.count_pptx_slides(pptx_path), result["slideCount"])
        warnings = result.get("warnings", [])
        self.assertFalse(any("模板页数" in warning for warning in warnings))

    def test_exam_flow(self):
        """从教学方案生成试卷 → 预览 → 导出 → 读取内容。"""
        # 先通过 API 生成教学方案
        templates = self.client.get("/api/v1/templates", headers=self.auth_headers())
        templates_json = templates.get_json()["data"]
        plan_template = next(item for item in templates_json["list"] if item["templateType"] == "THEORY")

        create_plan = self.client.post(
            "/api/v1/generation/plans",
            headers=self.auth_headers(),
            json={
                "templateId": plan_template["templateId"],
                "courseName": "水文地质学",
                "hours": 16,
                "audience": "本科二年级",
                "goals": ["掌握水文地质基本概念", "理解地下水运动规律"],
                "focusPoints": ["地下水补给与排泄", "含水层特征"],
            },
        )
        self.assertEqual(create_plan.status_code, 200)
        plan_task = create_plan.get_json()["data"]
        self.assertEqual(plan_task["status"], "SUCCESS")
        plan_id = plan_task["result"]["targetId"]

        # 基于方案生成试卷
        create_exam = self.client.post(
            "/api/v1/generation/exams",
            headers=self.auth_headers(),
            json={"planId": plan_id},
        )
        self.assertEqual(create_exam.status_code, 200)
        exam_task = create_exam.get_json()["data"]
        self.assertEqual(exam_task["status"], "SUCCESS")
        self.assertEqual(exam_task["result"]["targetType"], "EXAM")
        exam_id = exam_task["result"]["targetId"]
        self.assertGreater(exam_task["result"]["examInfo"]["totalScore"], 0)
        self.assertGreater(exam_task["result"]["examInfo"]["questionCount"], 0)

        # 读取试卷内容
        content_resp = self.client.get(f"/api/v1/content/EXAM/{exam_id}", headers=self.auth_headers())
        self.assertEqual(content_resp.status_code, 200)
        exam_content = content_resp.get_json()["data"]["content"]
        self.assertIn("questions", exam_content)
        self.assertGreater(len(exam_content["questions"]), 0)

        # 验证题型齐全
        qtypes = {q["type"] for q in exam_content["questions"]}
        self.assertIn("SINGLE_CHOICE", qtypes)
        self.assertIn("TRUE_FALSE", qtypes)
        self.assertIn("FILL_BLANK", qtypes)
        self.assertIn("SHORT_ANSWER", qtypes)
        self.assertIn("ESSAY", qtypes)

        # 验证题号连续
        numbers = [q["number"] for q in exam_content["questions"]]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))

        # 预览试卷
        preview = self.client.get(exam_task["result"]["previewUrl"], headers=self.auth_headers())
        self.assertEqual(preview.status_code, 200)
        preview_html = preview.get_data(as_text=True)
        self.assertIn(exam_content["course_name"], preview_html)
        self.assertIn("考试试卷", preview_html)
        preview.close()

        # 导出试卷为 Markdown
        export_resp = self.client.post(
            "/api/v1/exports",
            headers=self.auth_headers(),
            json={"targetId": exam_id, "format": "md", "expiryDays": 3, "shareScope": "private"},
        )
        self.assertEqual(export_resp.status_code, 200)
        download_url = export_resp.get_json()["data"]["downloadUrl"]
        download = self.client.get(download_url, headers=self.auth_headers())
        self.assertEqual(download.status_code, 200)
        download_md = download.get_data(as_text=True)
        self.assertIn(exam_content["course_name"], download_md)
        download.close()

        # 导出学生版（无答案）
        export_student = self.client.post(
            "/api/v1/exports",
            headers=self.auth_headers(),
            json={"targetId": exam_id, "format": "student_md", "expiryDays": 3, "shareScope": "public"},
        )
        self.assertEqual(export_student.status_code, 200)

        # 导出 JSON
        export_json = self.client.post(
            "/api/v1/exports",
            headers=self.auth_headers(),
            json={"targetId": exam_id, "format": "json", "expiryDays": 3, "shareScope": "private"},
        )
        self.assertEqual(export_json.status_code, 200)

    def test_template_version_rollback_and_user_admin(self):
        admin_token = self.login("admin", "admin123")["token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        upload_template = self.client.post(
            "/api/v1/templates/upload",
            headers=admin_headers,
            data={
                "type": "THEORY",
                "name": "版本化模板",
                "rulesJson": "{\"required_sections\":[\"教学目标\",\"教学流程\"]}",
                "file": (io.BytesIO("## {{ course_name }}".encode("utf-8")), "versioned_template.md"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_template.status_code, 200)
        template_id = upload_template.get_json()["data"]["templateId"]
        self.assertEqual(upload_template.get_json()["data"]["versionNo"], 1)

        upload_version = self.client.post(
            f"/api/v1/templates/{template_id}/versions",
            headers=admin_headers,
            data={
                "changeLog": "补充授课对象占位符",
                "file": (io.BytesIO("## {{ course_name }}\n{{ audience }}".encode("utf-8")), "versioned_template_v2.md"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_version.status_code, 200)
        version_detail = upload_version.get_json()["data"]
        self.assertEqual(version_detail["versionNo"], 2)
        self.assertEqual(len(version_detail["versionHistory"]), 2)

        rollback = self.client.post(
            f"/api/v1/templates/{template_id}/rollback",
            headers=admin_headers,
            json={"versionNo": 1},
        )
        self.assertEqual(rollback.status_code, 200)
        self.assertEqual(rollback.get_json()["data"]["versionNo"], 1)

        roles = self.client.get("/api/v1/roles", headers=admin_headers)
        self.assertEqual(roles.status_code, 200)
        self.assertGreaterEqual(len(roles.get_json()["data"]), 3)

        create_user = self.client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "username": "teacher02",
                "password": "teacher02",
                "realName": "新教师",
                "dept": "水利工程系",
                "roleCode": "TEACHER",
                "status": 1,
            },
        )
        self.assertEqual(create_user.status_code, 200)
        user_id = create_user.get_json()["data"]["userId"]

        update_user = self.client.patch(
            f"/api/v1/users/{user_id}",
            headers=admin_headers,
            json={"dept": "教学研究室", "status": 0},
        )
        self.assertEqual(update_user.status_code, 200)
        self.assertEqual(update_user.get_json()["data"]["dept"], "教学研究室")
        self.assertEqual(update_user.get_json()["data"]["status"], 0)

        audit_logs = self.client.get("/api/v1/audit-logs?size=10", headers=admin_headers)
        self.assertEqual(audit_logs.status_code, 200)
        audit_items = audit_logs.get_json()["data"]["list"]
        self.assertTrue(any(item["action"] == "USER_UPDATE" for item in audit_items))


if __name__ == "__main__":
    unittest.main()
