import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import Config
from backend.app.documents import build_courseware, build_teaching_plan, validate_courseware, validate_plan


def ok(data=None, message="ok"):
    return jsonify({"code": 0, "message": message, "data": {} if data is None else data})


def create_generation_app(config_overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    @app.get("/api/v1/health")
    def health():
        return ok({"status": "UP", "service": "python-generation-service"})

    @app.post("/api/v1/generate/plan")
    def generate_plan():
        payload = request.get_json(silent=True) or {}
        plan = build_teaching_plan(payload.get("params") or {}, payload.get("templateMeta") or {})
        return ok({"plan": plan})

    @app.post("/api/v1/generate/courseware")
    def generate_courseware():
        payload = request.get_json(silent=True) or {}
        courseware = build_courseware(
            payload.get("plan") or {},
            payload.get("templateMeta") or {},
            payload.get("resources") or [],
        )
        return ok({"courseware": courseware})

    @app.post("/api/v1/validate/plan")
    def validate_plan_result():
        payload = request.get_json(silent=True) or {}
        validation = validate_plan(payload.get("plan") or {}, payload.get("rules") or {})
        return ok({"validation": validation})

    @app.post("/api/v1/validate/courseware")
    def validate_courseware_result():
        payload = request.get_json(silent=True) or {}
        validation = validate_courseware(payload.get("courseware") or {}, payload.get("rules") or {})
        return ok({"validation": validation})

    @app.errorhandler(Exception)
    def handle_exception(error):
        app.logger.exception("Unhandled generation service error", exc_info=error)
        return jsonify({"code": 5000, "message": str(error), "data": {}}), 500

    return app


app = create_generation_app()


if __name__ == "__main__":
    port = int(os.getenv("WATER_GENERATION_SERVICE_PORT", str(Config.GENERATION_SERVICE_PORT)))
    app.run(host="127.0.0.1", port=port, debug=True)
