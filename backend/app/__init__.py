from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from .config import Config
from .errors import ServiceError
from .routes import register_routes
from .services import bootstrap


def create_app(config_overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    bootstrap(app)
    register_routes(app)

    @app.errorhandler(ServiceError)
    def handle_service_error(error):
        return jsonify(error.to_dict()), error.status

    @app.errorhandler(413)
    def handle_file_too_large(_error):
        return jsonify({"code": 1000, "message": "上传文件过大"}), 413

    @app.errorhandler(Exception)
    def handle_exception(error):
        if isinstance(error, HTTPException):
            return error
        app.logger.exception("Unhandled application error", exc_info=error)
        if request.path.startswith("/api/") or request.path.startswith("/share/"):
            return jsonify({"code": 5000, "message": "系统内部错误"}), 500
        raise error

    return app
