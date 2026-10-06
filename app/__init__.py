"""ShopMotion — privacy-first in-store customer behaviour analytics."""
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, render_template, request

from config import config_by_name

from .extensions import csrf, db, login_manager, migrate

__version__ = "1.0.0"


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_by_name[config_name])

    _configure_logging(app)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(app.root_path + "/../migrations"))
    csrf.init_app(app)
    login_manager.init_app(app)

    from .api import api_bp
    from .auth import auth_bp
    from .main import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    from .cli import register_cli
    register_cli(app)

    @app.context_processor
    def inject_globals():
        from .models import Alert
        try:
            open_alerts = Alert.query.filter_by(resolved=False).count()
        except Exception:  # tables not created yet
            open_alerts = 0
        return {"app_version": __version__, "open_alert_count": open_alerts,
                "now_year": datetime.now().year}

    @app.errorhandler(403)
    def forbidden(_):
        return _error(403, "You don't have permission to view this page.")

    @app.errorhandler(404)
    def not_found(_):
        return _error(404, "The page you are looking for doesn't exist.")

    if app.config["AUTO_CREATE_TABLES"]:
        from .seed import ensure_defaults

        with app.app_context():
            db.create_all()
            if not app.testing:
                ensure_defaults()

    return app


def _error(code: int, message: str):
    if request.path.startswith("/api/"):
        return jsonify(error=message), code
    return render_template("error.html", code=code, message=message), code


def _configure_logging(app: Flask) -> None:
    level = getattr(logging, app.config["LOG_LEVEL"].upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    log_file = app.config.get("LOG_FILE")
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        handler.setLevel(level)
        logging.getLogger().addHandler(handler)
