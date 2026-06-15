import io
import tempfile
import time
import unittest
from pathlib import Path

from backend.app import create_app


class BackendSecurityAndInterfaceTestCase(unittest.TestCase):
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

    def tearDown(self):
        self.temp_dir.cleanup()

    def login(self, username="teacher", password="teacher123"):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password, "captcha": "2026"},
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["data"]["token"]

    def headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_protected_api_rejects_missing_token(self):
        response = self.client.get("/api/v1/templates")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["code"], 1001)

    def test_student_cannot_upload_template_or_manage_users(self):
        token = self.login("student", "student123")

        upload_response = self.client.post(
            "/api/v1/templates/upload",
            headers=self.headers(token),
            data={
                "type": "THEORY",
                "name": "student-template",
                "file": (io.BytesIO(b"## {{ course_name }}"), "template.md"),
            },
            content_type="multipart/form-data",
        )
        users_response = self.client.get("/api/v1/users", headers=self.headers(token))

        self.assertEqual(upload_response.status_code, 403)
        self.assertEqual(users_response.status_code, 403)

    def test_invalid_template_type_returns_business_error(self):
        token = self.login()

        response = self.client.post(
            "/api/v1/templates/upload",
            headers=self.headers(token),
            data={
                "type": "BAD_TYPE",
                "name": "invalid-template",
                "file": (io.BytesIO(b"## {{ course_name }}"), "template.md"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], 1000)

    def test_generation_service_contract_endpoints(self):
        from backend.generation_service import create_generation_app

        app = create_generation_app(
            {
                "TESTING": True,
                "DATA_DIR": str(Path("backend/data").resolve()),
            }
        )
        client = app.test_client()

        health = client.get("/api/v1/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["data"]["service"], "python-generation-service")

        plan = client.post(
            "/api/v1/generate/plan",
            json={
                "params": {
                    "courseName": "水利工程概论",
                    "hours": 2,
                    "audience": "本科生",
                    "goals": ["理解水利工程基本任务"],
                    "focusPoints": ["水资源调度"],
                },
                "templateMeta": {"template_type": "THEORY", "template_name": "理论课模板"},
            },
        )
        self.assertEqual(plan.status_code, 200)
        self.assertIn("plan", plan.get_json()["data"])

    def test_plan_generation_completes_within_local_threshold(self):
        token = self.login()
        templates = self.client.get("/api/v1/templates", headers=self.headers(token)).get_json()["data"]["list"]
        template_id = next(item["templateId"] for item in templates if item["templateType"] == "THEORY")

        start = time.perf_counter()
        response = self.client.post(
            "/api/v1/generation/plans",
            headers=self.headers(token),
            json={
                "templateId": template_id,
                "courseName": "水利工程概论",
                "hours": 2,
                "audience": "本科生",
                "goals": ["理解水利工程基本任务"],
                "focusPoints": ["水资源调度"],
            },
        )
        elapsed = time.perf_counter() - start

        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 3.0)


if __name__ == "__main__":
    unittest.main()
