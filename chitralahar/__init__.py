"""Chitralahar — an elegant, minimal photography portfolio CMS."""
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config


def _get_or_create_secret_key(instance_dir: Path) -> str:
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_file = instance_dir / ".secret_key"
    if key_file.exists():
        try:
            os.chmod(key_file, 0o600)  # tighten if an older version left it world-readable
        except OSError:
            pass
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    try:
        # Atomic, owner-only (0600) create. If another worker won the race,
        # read whatever landed on disk so all workers share one key.
        fd = os.open(key_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(key)
        return key
    except FileExistsError:
        return key_file.read_text(encoding="utf-8").strip()


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Behind Apache/nginx: trust ONE proxy hop for scheme/host/client-IP so HTTPS
    # detection (Secure cookie), url_for(_external=...) and rate-limit IPs are right.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Runtime directories: instance (db + secret) and uploads.
    instance_dir = Path(app.config["DATABASE"]).parent
    instance_dir.mkdir(parents=True, exist_ok=True)
    upload_root = Path(app.config["UPLOAD_FOLDER"])
    for sub in ("photos", "thumbs", "misc", "wm", "originals"):
        (upload_root / sub).mkdir(parents=True, exist_ok=True)

    app.config["SECRET_KEY"] = _get_or_create_secret_key(instance_dir)

    # Database wiring + auto-initialization (idempotent).
    from . import db as db_module

    db_module.init_app(app)
    with app.app_context():
        db_module.init_db()

    # Jinja filters.
    from .utils import clean_html, format_date, render_markdown

    app.jinja_env.filters["markdown"] = render_markdown
    app.jinja_env.filters["clean_html"] = clean_html
    app.jinja_env.filters["dateformat"] = format_date

    # Blueprints.
    from .admin import bp as admin_bp
    from .auth import bp as auth_bp
    from .public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    # Globals available to every template.
    from .auth import current_user
    from .db import get_settings
    from .public import build_public_menu

    from datetime import datetime

    @app.context_processor
    def inject_globals():
        return {
            "site": get_settings(),
            "current_user": current_user(),
            "now_year": datetime.now().year,
            "menu": build_public_menu,  # callable: only invoked by the public base
        }

    # Security response headers (applied to every response).
    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        # Don't leak private /private/<token> share links via the Referer header.
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'self'; object-src 'none'; base-uri 'self'",
        )
        return resp

    # Lightweight CSRF defense-in-depth: SameSite=Lax already blocks cross-site
    # cookie sending; this also rejects any state-changing request whose Origin is
    # a different host. Requests with no Origin header are left to SameSite.
    @app.before_request
    def _csrf_origin_guard():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("Origin")
            if origin and urlparse(origin).netloc != request.host:
                abort(403)

    # Error handling.
    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def too_large(_e):
        limit = app.config.get("MAX_CONTENT_LENGTH")
        if limit:
            flash(f"Upload too large — the limit is {limit // (1024 * 1024)} MB per request.", "error")
        else:
            flash("Upload too large.", "error")
        ref = request.referrer or ""
        if ref and urlparse(ref).netloc == request.host:  # same-origin only
            return redirect(ref)
        return redirect(url_for("admin.photos"))

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("500.html"), 500

    @app.errorhandler(Exception)
    def unhandled(e):
        if isinstance(e, HTTPException):
            return e  # 404/413/403/… keep their own responses
        app.logger.exception("Unhandled application error")
        return render_template("500.html"), 500

    return app
