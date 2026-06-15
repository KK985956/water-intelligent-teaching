import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app import create_app
from backend.app.database import execute, fetch_one
from backend.app.documents import build_courseware
from backend.app.services import json_dumps, make_id, now_text, seed_defaults


def sample_plan():
    return {
        "course_name": "\u667a\u6167\u6c34\u5229\u7cfb\u7edf\u5bfc\u8bba",
        "template_name": "\u6807\u51c6\u6559\u5b66\u65b9\u6848",
        "course_type": "THEORY",
        "course_type_label": "\u7406\u8bba\u8bfe",
        "hours": 8,
        "audience": "\u6c34\u5229\u5de5\u7a0b\u4e13\u4e1a\u672c\u79d1\u751f",
        "goals": [
            "\u80fd\u591f\u8bf4\u660e\u667a\u6167\u6c34\u5229\u7684\u7cfb\u7edf\u67b6\u6784\u4e0e\u5173\u952e\u6280\u672f",
            "\u80fd\u591f\u8bfb\u61c2\u6c34\u60c5\u76d1\u6d4b\u6570\u636e\u5e76\u5224\u65ad\u5de5\u7a0b\u8c03\u5ea6\u98ce\u9669",
            "\u80fd\u591f\u7ed3\u5408\u6848\u4f8b\u8bbe\u8ba1\u4e00\u4e2a\u7b80\u5316\u7684\u6559\u5b66\u6f14\u793a\u65b9\u6848",
        ],
        "focus_points": [
            "\u6c34\u5229\u6570\u636e\u91c7\u96c6\u4e0e\u4f20\u8f93",
            "\u6d2a\u6c34\u9884\u8b66\u4e0e\u8c03\u5ea6\u51b3\u7b56",
        ],
        "difficult_points": [
            "\u591a\u6e90\u6570\u636e\u878d\u5408\u540e\u7684\u6559\u5b66\u5efa\u6a21",
            "\u5de5\u7a0b\u6848\u4f8b\u5230\u8bfe\u5802\u6d3b\u52a8\u7684\u8f6c\u5316",
        ],
        "cases": [
            "\u67d0\u6d41\u57df\u96e8\u6c34\u60c5\u76d1\u6d4b\u4e0e\u9884\u8b66\u6848\u4f8b",
            "\u6c34\u5e93\u8054\u5408\u8c03\u5ea6\u8bfe\u5802\u6a21\u62df\u6848\u4f8b",
        ],
        "exercises": [
            "\u5206\u7ec4\u5224\u8bfb\u4e00\u7ec4\u6c34\u4f4d\u6d41\u91cf\u66f2\u7ebf",
            "\u4e3a\u96e8\u6c34\u60c5\u76d1\u6d4b\u573a\u666f\u8bbe\u8ba1\u4e09\u4e2a\u8bfe\u5802\u63d0\u95ee",
        ],
        "homework": [
            "\u5b8c\u6210\u4e00\u9875\u667a\u6167\u6c34\u5229\u8bfe\u5802\u6848\u4f8b\u5206\u6790",
        ],
        "summary": "\u672c\u8bfe\u901a\u8fc7\u67b6\u6784\u3001\u6570\u636e\u3001\u6848\u4f8b\u548c\u7ec3\u4e60\u5efa\u7acb\u667a\u6167\u6c34\u5229\u6559\u5b66\u95ed\u73af\u3002",
        "outline": [
            {
                "title": "\u95ee\u9898\u5bfc\u5165",
                "duration": "10\u5206\u949f",
                "content": "\u4ece\u6d41\u57df\u9632\u6c5b\u573a\u666f\u5f15\u51fa\u667a\u6167\u6c34\u5229\u5b66\u4e60\u4efb\u52a1",
                "method": "\u60c5\u5883\u5bfc\u5165",
                "knowledge_points": ["\u9632\u6c5b\u8c03\u5ea6", "\u6570\u636e\u611f\u77e5"],
            },
            {
                "title": "\u6982\u5ff5\u5efa\u6784",
                "duration": "25\u5206\u949f",
                "content": "\u8bb2\u89e3\u611f\u77e5\u5c42\u3001\u7f51\u7edc\u5c42\u3001\u5e73\u53f0\u5c42\u4e0e\u5e94\u7528\u5c42",
                "method": "\u8bb2\u6388\u4e0e\u56fe\u89e3",
                "knowledge_points": ["\u7cfb\u7edf\u67b6\u6784", "\u7269\u8054\u7f51", "\u6570\u636e\u5e73\u53f0"],
            },
            {
                "title": "\u6848\u4f8b\u7814\u8ba8",
                "duration": "30\u5206\u949f",
                "content": "\u5206\u6790\u6c34\u5e93\u8054\u5408\u8c03\u5ea6\u4e2d\u7684\u6570\u636e\u3001\u6a21\u578b\u4e0e\u51b3\u7b56",
                "method": "\u5c0f\u7ec4\u7814\u8ba8",
                "knowledge_points": ["\u9884\u62a5\u6a21\u578b", "\u8c03\u5ea6\u89c4\u5219", "\u98ce\u9669\u5224\u65ad"],
            },
        ],
    }


class CoursewareEnhancementTestCase(unittest.TestCase):
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

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_local_courseware_is_readable_and_teaching_rich(self):
        courseware = build_courseware(sample_plan(), {"templateName": "\u667a\u6167\u8bfe\u4ef6\u6a21\u677f"}, [])
        text = json.dumps(courseware, ensure_ascii=False)

        self.assertGreaterEqual(courseware["slide_count"], 8)
        self.assertNotIn("??", text)
        self.assertNotIn("\ufffd", text)
        self.assertTrue(all(slide.get("image_prompt") for slide in courseware["slides"]))
        self.assertTrue(all(slide.get("speaker_notes") for slide in courseware["slides"]))
        self.assertTrue(any("\u6559\u5b66\u76ee\u6807" in slide["title"] for slide in courseware["slides"]))
        self.assertTrue(any("\u91cd\u70b9" in slide["title"] for slide in courseware["slides"]))
        self.assertTrue(any("\u8bfe\u5802\u7ec3\u4e60" in slide["title"] for slide in courseware["slides"]))

    def test_courseware_generation_writes_generated_image_paths(self):
        with self.app.app_context():
            seed_defaults()
            template = fetch_one("SELECT * FROM t_template WHERE template_type = 'TRAINING' LIMIT 1")
            plan_id = make_id("PLAN")
            task_id = make_id("TASK")
            execute(
                """
                INSERT INTO t_generation_task(task_id, task_type, user_id, template_id, params_json, status, progress, created_at, updated_at)
                VALUES (?, 'COURSEWARE', 'U-TEACHER', ?, ?, 'PENDING', 0, ?, ?)
                """,
                (
                    task_id,
                    template["template_id"],
                    json_dumps({"planId": plan_id, "resources": []}),
                    now_text(),
                    now_text(),
                ),
            )
            execute(
                """
                INSERT INTO t_teaching_plan(plan_id, task_id, course_name, course_type, outline_json, goals_text, key_points,
                    validate_status, file_path, preview_path, content_json, created_at)
                VALUES (?, ?, ?, 'THEORY', ?, ?, ?, 'PASS', '', '', ?, ?)
                """,
                (
                    plan_id,
                    task_id,
                    sample_plan()["course_name"],
                    json_dumps(sample_plan()["outline"]),
                    "\n".join(sample_plan()["goals"]),
                    "\uff1b".join(sample_plan()["focus_points"]),
                    json_dumps(sample_plan()),
                    now_text(),
                ),
            )
            task = fetch_one("SELECT * FROM t_generation_task WHERE task_id = ?", (task_id,))

            png_bytes = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
            )

            def fake_generate_slide_image(prompt, output_path):
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(png_bytes)
                return output_path

            self.app.config["OPENAI_IMAGE_ENABLED"] = True
            with patch("backend.app.services.generate_slide_image", side_effect=fake_generate_slide_image):
                from backend.app.services import _build_courseware_result

                result_meta, _ = _build_courseware_result(task)

        courseware = json.loads(Path(result_meta["files"]["json"]).read_text(encoding="utf-8"))
        image_paths = [slide.get("image_path") for slide in courseware["slides"] if slide.get("image_path")]
        self.assertGreater(len(image_paths), 0)
        self.assertTrue(all(Path(path).exists() for path in image_paths))


if __name__ == "__main__":
    unittest.main()
