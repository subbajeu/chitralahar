"""Authentication: first-run setup, login, logout, and the login guard."""
import functools

from flask import (
    Blueprint, current_app, flash, g, redirect, render_template, request, session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .ratelimit import record_failure, reset, too_many

bp = Blueprint("auth", __name__)


def user_count(db) -> int:
    return db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]


def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    if "user" not in g:
        g.user = get_db().execute(
            "SELECT id, username FROM users WHERE id = ?", (uid,)
        ).fetchone()
    return g.user


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if user_count(get_db()) == 0:
            return redirect(url_for("auth.setup"))
        if current_user() is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def _safe_next(target: str) -> str:
    """Only allow same-site relative redirects (reject //host and \\host tricks)."""
    normalized = (target or "").replace("\\", "/")
    if normalized.startswith("/") and not normalized.startswith("//"):
        return target
    return url_for("admin.dashboard")


@bp.route("/admin/setup", methods=["GET", "POST"])
def setup():
    db = get_db()
    if user_count(db) > 0:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        if not username:
            flash("Choose a username.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            db.execute(
                "INSERT INTO users(username, password_hash) VALUES (?, ?)",
                # pbkdf2 is always available; scrypt is missing in some Python builds.
                (username, generate_password_hash(password, method="pbkdf2:sha256")),
            )
            db.commit()
            user = db.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            flash("Welcome to Chitralahar — your admin account is ready.", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/setup.html")


@bp.route("/admin/login", methods=["GET", "POST"])
def login():
    db = get_db()
    if user_count(db) == 0:
        return redirect(url_for("auth.setup"))
    if request.method == "POST":
        ip = request.remote_addr or "?"
        key = "login:" + ip
        if too_many(key):
            current_app.logger.warning("Rate-limited admin login from %s", ip)
            flash("Too many attempts. Please wait a few minutes and try again.", "error")
            return render_template("admin/login.html"), 429
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            record_failure(key)
            current_app.logger.warning("Failed admin login for %r from %s", username, ip)
            flash("Incorrect username or password.", "error")
        else:
            reset(key)
            session.clear()
            if user["totp_secret"]:
                # Password OK but 2FA is on: park the login until a code is given.
                session["2fa_user"] = user["id"]
                return redirect(url_for("auth.login_2fa", next=request.args.get("next", "")))
            session["user_id"] = user["id"]
            session.permanent = True
            return redirect(_safe_next(request.args.get("next", "")))
    return render_template("admin/login.html")


@bp.route("/admin/login/2fa", methods=["GET", "POST"])
def login_2fa():
    from .totp import verify
    uid = session.get("2fa_user")
    if uid is None:
        return redirect(url_for("auth.login"))
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if user is None or not user["totp_secret"]:
        session.clear()
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        ip = request.remote_addr or "?"
        key = "2fa:" + ip
        if too_many(key):
            current_app.logger.warning("Rate-limited 2FA from %s", ip)
            flash("Too many attempts. Please wait a few minutes.", "error")
            return render_template("admin/login_2fa.html"), 429
        counter = verify(user["totp_secret"], request.form.get("code"), user["totp_counter"])
        if counter:
            reset(key)
            db.execute("UPDATE users SET totp_counter = ? WHERE id = ?", (counter, uid))
            db.commit()
            session.clear()
            session["user_id"] = uid
            session.permanent = True
            return redirect(_safe_next(request.args.get("next", "")))
        record_failure(key)
        current_app.logger.warning("Failed 2FA code for user %s from %s", user["username"], ip)
        flash("That code isn't right — check your authenticator app.", "error")
    return render_template("admin/login_2fa.html")


@bp.route("/admin/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("public.home"))
