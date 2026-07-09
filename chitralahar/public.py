"""Public-facing portfolio, blog, and about pages."""
import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

from flask import (
    Blueprint, Response, abort, current_app, flash, jsonify, redirect,
    render_template, request, send_file, session, url_for,
)
from markupsafe import escape
from werkzeug.security import check_password_hash

from .db import get_db, get_settings, photo_tags, resolve_tag
from .ratelimit import record_failure, reset, too_many
from .utils import make_slug

bp = Blueprint("public", __name__)

# The single publish-cascade gate, reused by EVERY public photo query (list,
# single, prev, next) so they can never diverge and leak a hidden photo.
# A photo is public only if it is published AND its category (if any) is
# published AND its subcategory (if any) and that subcategory's parent are too.
_VISIBLE = """
  FROM photos p
  LEFT JOIN categories c ON c.id = p.category_id
  LEFT JOIN subcategories s ON s.id = p.subcategory_id
  LEFT JOIN categories sp ON sp.id = s.category_id
  WHERE p.published = 1
    AND (p.category_id IS NULL OR (c.published = 1 AND c.private = 0))
    AND (p.subcategory_id IS NULL OR (s.published = 1 AND s.private = 0
                                      AND sp.published = 1 AND sp.private = 0))
"""

_ORDER = " ORDER BY p.sort_order, p.created_at DESC, p.id DESC"


def _visible_photos(db, extra="", params=()):
    return db.execute("SELECT p.* " + _VISIBLE + extra + _ORDER, params).fetchall()


def _category_chips(db):
    """Published categories that have at least one publicly visible photo."""
    return db.execute(
        """SELECT c.id, c.name, c.slug FROM categories c
           WHERE c.published = 1 AND c.private = 0 AND EXISTS (
             SELECT 1 FROM photos p
             LEFT JOIN subcategories s2 ON s2.id = p.subcategory_id
             WHERE p.published = 1 AND (
               p.category_id = c.id
               OR (s2.id IS NOT NULL AND s2.category_id = c.id AND s2.published = 1)
             ))
           ORDER BY c.sort_order, c.name COLLATE NOCASE"""
    ).fetchall()


def _subcategory_chips(db, cat_id):
    """Published subcategories of a category that have a visible photo."""
    return db.execute(
        """SELECT s.id, s.name, s.slug FROM subcategories s
           JOIN categories c ON c.id = s.category_id
           WHERE s.category_id = ? AND s.published = 1 AND s.private = 0 AND c.published = 1
             AND EXISTS (SELECT 1 FROM photos p
                         WHERE p.subcategory_id = s.id AND p.published = 1)
           ORDER BY s.sort_order, s.name COLLATE NOCASE""",
        (cat_id,),
    ).fetchall()


def resolve_public_category(db, slug):
    return db.execute(
        "SELECT * FROM categories WHERE slug = ? AND published = 1 AND private = 0", (slug,)
    ).fetchone()


def resolve_public_subcategory(db, cat_id, subslug):
    return db.execute(
        """SELECT s.* FROM subcategories s JOIN categories c ON c.id = s.category_id
           WHERE s.category_id = ? AND s.slug = ? AND s.published = 1 AND s.private = 0
             AND c.published = 1 AND c.private = 0""",
        (cat_id, subslug),
    ).fetchone()


def _menu_active(link_type, href):
    ep = request.endpoint or ""
    if link_type == "home":
        return ep in ("public.home", "public.category", "public.subcategory")
    if link_type == "blog":
        return ep in ("public.blog", "public.post")
    if link_type == "about":
        return ep == "public.about"
    if link_type == "contact":
        return ep == "public.contact"
    return request.path == href


def build_public_menu():
    """Resolve the published menu into a tree of nav nodes for the header.

    Each node is {label, href, external, active, children}. Items pointing at a
    hidden category/subcategory (or a child of a hidden parent) are dropped, so
    the menu never links to something the public cannot see.
    """
    db = get_db()
    rows = db.execute(
        """SELECT m.*, c.slug AS cat_slug, c.published AS cat_pub, c.private AS cat_private,
                  s.slug AS sub_slug, s.published AS sub_pub, s.private AS sub_private,
                  ps.slug AS sub_parent_slug, ps.published AS sub_parent_pub,
                  ps.private AS sub_parent_private
           FROM menu_items m
           LEFT JOIN categories c ON c.id = m.category_id
           LEFT JOIN subcategories s ON s.id = m.subcategory_id
           LEFT JOIN categories ps ON ps.id = s.category_id
           WHERE m.published = 1
           ORDER BY m.sort_order, m.id"""
    ).fetchall()

    def href_for(m):
        lt = m["link_type"]
        if lt == "home":
            return url_for("public.home"), False
        if lt == "blog":
            return url_for("public.blog"), False
        if lt == "about":
            return url_for("public.about"), False
        if lt == "contact":
            return url_for("public.contact"), False
        if lt == "category" and m["cat_slug"] and m["cat_pub"] and not m["cat_private"]:
            return url_for("public.category", slug=m["cat_slug"]), False
        if (lt == "subcategory" and m["sub_slug"] and m["sub_pub"] and not m["sub_private"]
                and m["sub_parent_pub"] and not m["sub_parent_private"]):
            return url_for("public.subcategory",
                           slug=m["sub_parent_slug"], subslug=m["sub_slug"]), False
        if lt == "url":
            u = (m["url"] or "").strip()
            if u:
                return u, u.startswith(("http://", "https://"))
        return None, False

    resolved = {}
    for m in rows:
        href, external = href_for(m)
        if not href:
            continue
        resolved[m["id"]] = {
            "label": m["label"], "href": href, "external": external,
            "active": _menu_active(m["link_type"], href), "children": [],
        }

    tops = []
    for m in rows:
        node = resolved.get(m["id"])
        if node is None:
            continue
        pid = m["parent_id"]
        if pid and pid in resolved:
            resolved[pid]["children"].append(node)
        elif not pid:
            tops.append(node)
    for t in tops:
        if t["children"] and any(ch["active"] for ch in t["children"]):
            t["active"] = True
    return tops


@bp.route("/")
def home():
    db = get_db()
    legacy = (request.args.get("c") or "").strip()
    if legacy:  # 301 shim for old ?c=<name|slug> bookmarks (published only)
        cat = db.execute(
            "SELECT slug FROM categories "
            "WHERE published = 1 AND (slug = ? OR name = ? COLLATE NOCASE)",
            (legacy, legacy),
        ).fetchone()
        if cat:
            return redirect(url_for("public.category", slug=cat["slug"]), code=301)

    # The home gallery's content is admin-controlled: all photos, only featured,
    # or a single chosen category.
    settings = get_settings()
    show = settings.get("home_show", "all")
    if show == "featured":
        photos = _visible_photos(db, " AND p.featured = 1")
    elif show == "category":
        try:
            cid = int(settings.get("home_category") or 0)
        except (TypeError, ValueError):
            cid = 0
        public_cat = cid and db.execute(
            "SELECT 1 FROM categories WHERE id = ? AND published = 1 AND private = 0", (cid,)
        ).fetchone()
        photos = _visible_photos(db, " AND p.category_id = ?", (cid,)) if public_cat else _visible_photos(db)
    else:
        photos = _visible_photos(db)

    # The "slider" template opens the home page with a slideshow of featured photos.
    slides = _visible_photos(db, " AND p.featured = 1") if settings.get("template") == "slider" else []

    return render_template(
        "public/home.html",
        photos=photos,
        categories=_category_chips(db),
        subcategories=None,
        active_cat=None,
        active_sub=None,
        slides=slides,
    )


@bp.route("/category/<slug>")
def category(slug):
    db = get_db()
    cat = resolve_public_category(db, slug)
    if cat is None:
        abort(404)
    return render_template(
        "public/home.html",
        photos=_visible_photos(db, " AND p.category_id = ?", (cat["id"],)),
        categories=_category_chips(db),
        subcategories=_subcategory_chips(db, cat["id"]),
        active_cat=cat,
        active_sub=None,
    )


@bp.route("/category/<slug>/<subslug>")
def subcategory(slug, subslug):
    db = get_db()
    cat = resolve_public_category(db, slug)
    if cat is None:
        abort(404)
    sub = resolve_public_subcategory(db, cat["id"], subslug)
    if sub is None:
        abort(404)
    return render_template(
        "public/home.html",
        photos=_visible_photos(db, " AND p.subcategory_id = ?", (sub["id"],)),
        categories=_category_chips(db),
        subcategories=_subcategory_chips(db, cat["id"]),
        active_cat=cat,
        active_sub=sub,
    )


@bp.route("/tag/<slug>")
def tag(slug):
    db = get_db()
    t = resolve_tag(db, slug)
    if t is None:
        abort(404)
    photos = _visible_photos(
        db, " AND p.id IN (SELECT photo_id FROM photo_tags WHERE tag_id = ?)", (t["id"],)
    )
    return render_template("public/tag.html", tag=t, photos=photos)


@bp.route("/i/<int:photo_id>/<kind>")
def image(photo_id, kind):
    """Serve a public photo, watermarked + cached when the watermark is on.
    Only publicly-visible photos are reachable here; private albums keep using
    their own clean static files, so client downloads are never watermarked."""
    if kind not in ("full", "thumb"):
        abort(404)
    db = get_db()
    p = db.execute("SELECT p.* " + _VISIBLE + " AND p.id = ?", (photo_id,)).fetchone()
    if p is None:
        abort(404)
    sub = "photos" if kind == "full" else "thumbs"
    fname = p["filename"] if kind == "full" else p["thumb_filename"]
    clean = Path(current_app.config["UPLOAD_FOLDER"]) / sub / fname
    if not clean.exists():
        abort(404)
    settings = get_settings()
    if not settings.get("watermark_enabled"):
        return send_file(clean, max_age=2592000)
    from .images import watermarked_file
    return send_file(watermarked_file(clean, kind + "_" + fname, settings), max_age=2592000)


@bp.route("/photo/<int:photo_id>")
def photo(photo_id):
    db = get_db()
    p = db.execute(
        "SELECT p.*, c.name AS cat_name, c.slug AS cat_slug, "
        "s.name AS sub_name, s.slug AS sub_slug "
        + _VISIBLE + " AND p.id = ?",
        (photo_id,),
    ).fetchone()
    if p is None:
        abort(404)
    prev_p = db.execute(
        "SELECT p.id " + _VISIBLE
        + " AND (p.sort_order < ? OR (p.sort_order = ? AND p.id < ?)) "
        "ORDER BY p.sort_order DESC, p.id DESC LIMIT 1",
        (p["sort_order"], p["sort_order"], p["id"]),
    ).fetchone()
    next_p = db.execute(
        "SELECT p.id " + _VISIBLE
        + " AND (p.sort_order > ? OR (p.sort_order = ? AND p.id > ?)) "
        "ORDER BY p.sort_order ASC, p.id ASC LIMIT 1",
        (p["sort_order"], p["sort_order"], p["id"]),
    ).fetchone()
    exif = {}
    if get_settings().get("show_exif") and p["exif"]:
        try:
            exif = json.loads(p["exif"])
        except ValueError:
            pass
    return render_template("public/photo.html", photo=p, prev_p=prev_p, next_p=next_p,
                           tags=photo_tags(db, photo_id), exif=exif)


@bp.route("/blog")
def blog():
    db = get_db()
    posts = db.execute(
        "SELECT * FROM posts WHERE published = 1 "
        "ORDER BY COALESCE(published_at, created_at) DESC, id DESC"
    ).fetchall()
    return render_template("public/blog.html", posts=posts)


@bp.route("/blog/<slug>")
def post(slug):
    db = get_db()
    p = db.execute(
        "SELECT * FROM posts WHERE slug = ? AND published = 1", (slug,)
    ).fetchone()
    if p is None:
        abort(404)
    return render_template("public/post.html", post=p)


@bp.route("/about")
def about():
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE slug = 'about'").fetchone()
    return render_template("public/about.html", page=page)


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    db = get_db()
    if request.method == "POST":
        ip = request.remote_addr or "?"
        name = (request.form.get("name") or "").strip()[:200]
        email = (request.form.get("email") or "").strip()[:200]
        body = (request.form.get("message") or "").strip()[:5000]
        # honeypot: real users never fill "website"; bots do. Pretend success.
        if request.form.get("website") or too_many("contact:" + ip, max_attempts=5, window=3600):
            flash("Thanks — your message has been sent.", "success")
            return redirect(url_for("public.contact"))
        if not body or not (name or email):
            flash("Please add your name or email, and a message.", "error")
        else:
            record_failure("contact:" + ip, window=3600)  # counts sends per IP/hour
            db.execute("INSERT INTO messages(name, email, body) VALUES (?, ?, ?)",
                       (name, email, body))
            db.commit()
            flash("Thanks — your message has been sent.", "success")
            return redirect(url_for("public.contact"))
    page = db.execute("SELECT * FROM pages WHERE slug = 'contact'").fetchone()
    return render_template("public/contact.html", page=page)


# --------------------------- Private albums ---------------------------

def _resolve_private_album(db, token):
    """(album_row, is_subcategory) for a private share token, or (None, False)."""
    album = db.execute(
        "SELECT * FROM categories WHERE share_token = ? AND private = 1", (token,)
    ).fetchone()
    if album is not None:
        return album, False
    album = db.execute(
        "SELECT * FROM subcategories WHERE share_token = ? AND private = 1", (token,)
    ).fetchone()
    return album, (album is not None)


def _unlock_fingerprint(passkey):
    return hashlib.sha256(passkey.encode("utf-8")).hexdigest()[:16]


def _album_unlocked(album, token):
    """True if no passphrase, or the session holds the current passphrase's fingerprint.
    Binding to the hash means changing the passphrase re-locks existing sessions."""
    if not album["passkey"]:
        return True
    return session.get("unlocked_" + token) == _unlock_fingerprint(album["passkey"])


def _album_photos(db, album, is_sub):
    if is_sub:
        return db.execute(
            "SELECT p.* FROM photos p WHERE p.published = 1 AND p.subcategory_id = ? "
            "ORDER BY p.sort_order, p.created_at DESC, p.id DESC", (album["id"],)
        ).fetchall()
    return db.execute(
        """SELECT p.* FROM photos p
           LEFT JOIN subcategories s ON s.id = p.subcategory_id
           WHERE p.published = 1 AND p.category_id = ?
             AND (p.subcategory_id IS NULL OR s.published = 1)
           ORDER BY p.sort_order, p.created_at DESC, p.id DESC""", (album["id"],)
    ).fetchall()


@bp.route("/private/<token>", methods=["GET", "POST"])
def private_gallery(token):
    """A private client gallery, reachable only by its share link (+ optional passphrase)."""
    db = get_db()
    album, is_sub = _resolve_private_album(db, token)
    if album is None:
        abort(404)

    if not _album_unlocked(album, token):
        if request.method == "POST":
            ip = request.remote_addr or "?"
            key = "passphrase:%s:%s" % (token, ip)
            if too_many(key):
                current_app.logger.warning("Rate-limited private-gallery passphrase for %s from %s", token, ip)
                flash("Too many attempts. Please wait a few minutes and try again.", "error")
                return render_template("public/private_locked.html", cat=album), 429
            if check_password_hash(album["passkey"], request.form.get("passkey") or ""):
                reset(key)
                session["unlocked_" + token] = _unlock_fingerprint(album["passkey"])
                return redirect(url_for("public.private_gallery", token=token))
            record_failure(key)
            current_app.logger.warning("Failed private-gallery passphrase for %s from %s", token, ip)
            flash("Incorrect passphrase.", "error")
        return render_template("public/private_locked.html", cat=album)

    picked = {r["photo_id"] for r in db.execute(
        "SELECT photo_id FROM proof_selections WHERE token = ?", (token,)).fetchall()}
    return render_template("public/private.html", cat=album,
                           photos=_album_photos(db, album, is_sub), picked=picked)


@bp.route("/private/<token>/proof/<int:photo_id>", methods=["POST"])
def private_proof(token, photo_id):
    """Client proofing: toggle a favourite on a photo in an unlocked private album."""
    db = get_db()
    album, is_sub = _resolve_private_album(db, token)
    if album is None or not _album_unlocked(album, token):
        abort(404)
    field = "subcategory_id" if is_sub else "category_id"
    p = db.execute(f"SELECT 1 FROM photos WHERE id = ? AND {field} = ? AND published = 1",
                   (photo_id, album["id"])).fetchone()
    if p is None:
        abort(404)
    gone = db.execute("DELETE FROM proof_selections WHERE photo_id = ? AND token = ?",
                      (photo_id, token)).rowcount
    if not gone:
        db.execute("INSERT INTO proof_selections(photo_id, token) VALUES (?, ?)",
                   (photo_id, token))
    db.commit()
    return jsonify({"picked": not gone})


@bp.route("/private/<token>/img/<int:photo_id>/<kind>")
def private_image(token, photo_id, kind):
    """Serve a private album's image only to a viewer who has unlocked the album.
    This keeps private originals off the public /static path (so they can't be
    fetched by guessing the URL, bypassing the passphrase)."""
    if kind not in ("full", "thumb"):
        abort(404)
    db = get_db()
    album, is_sub = _resolve_private_album(db, token)
    if album is None or not _album_unlocked(album, token):
        abort(404)
    if is_sub:
        p = db.execute(
            "SELECT * FROM photos WHERE id = ? AND subcategory_id = ? AND published = 1",
            (photo_id, album["id"]),
        ).fetchone()
    else:
        p = db.execute(
            "SELECT p.* FROM photos p LEFT JOIN subcategories s ON s.id = p.subcategory_id "
            "WHERE p.id = ? AND p.category_id = ? AND p.published = 1 "
            "AND (p.subcategory_id IS NULL OR s.published = 1)",
            (photo_id, album["id"]),
        ).fetchone()
    if p is None:
        abort(404)
    sub = "photos" if kind == "full" else "thumbs"
    fname = p["filename"] if kind == "full" else p["thumb_filename"]
    path = Path(current_app.config["UPLOAD_FOLDER"]) / sub / fname
    if not path.exists():
        abort(404)
    # Private: tell shared caches not to store it.
    resp = send_file(path)
    resp.headers["Cache-Control"] = "private, max-age=0, no-store"
    return resp


@bp.route("/private/<token>/download")
def private_download(token):
    """ZIP of a private album's photos — only if the owner enabled downloads."""
    db = get_db()
    album, is_sub = _resolve_private_album(db, token)
    if album is None or not album["allow_download"]:
        abort(404)
    if not _album_unlocked(album, token):
        return redirect(url_for("public.private_gallery", token=token))

    photos = _album_photos(db, album, is_sub)
    root = Path(current_app.config["UPLOAD_FOLDER"])
    photos_dir, orig_dir = root / "photos", root / "originals"

    # Stream from a temp file rather than buffering the whole archive in RAM.
    # Prefer the full-resolution original; fall back to the display image.
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    count = 0
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
            for i, p in enumerate(photos, 1):
                keys = p.keys()
                of = p["orig_filename"] if "orig_filename" in keys else ""
                if of and (orig_dir / of).exists():
                    src = orig_dir / of
                    ext = of.rsplit(".", 1)[-1].lower() if "." in of else "jpg"
                else:
                    src = photos_dir / p["filename"]
                    ext = "jpg"
                if not src.exists():
                    continue
                base = make_slug(p["title"] or Path(p["orig_name"] or "").stem or "photo")
                zf.write(src, "%03d-%s.%s" % (i, base, ext))
                count += 1
        tmp.flush()
        tmp.close()
    except Exception:
        tmp.close()
        os.unlink(tmp.name)
        raise
    if not count:
        os.unlink(tmp.name)
        abort(404)

    resp = send_file(tmp.name, mimetype="application/zip", as_attachment=True,
                     download_name=(make_slug(album["name"]) or "album") + ".zip")
    resp.call_on_close(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
    return resp


# --------------------------- SEO & feeds ---------------------------

@bp.route("/robots.txt")
def robots():
    return Response(
        "User-agent: *\nDisallow: /admin\nDisallow: /private/\n"
        "Sitemap: %s\n" % url_for("public.sitemap", _external=True),
        mimetype="text/plain",
    )


@bp.route("/sitemap.xml")
def sitemap():
    db = get_db()
    urls = [url_for("public.home", _external=True),
            url_for("public.blog", _external=True),
            url_for("public.about", _external=True),
            url_for("public.contact", _external=True)]
    for c in _category_chips(db):
        urls.append(url_for("public.category", slug=c["slug"], _external=True))
        for s in _subcategory_chips(db, c["id"]):
            urls.append(url_for("public.subcategory", slug=c["slug"], subslug=s["slug"], _external=True))
    for p in db.execute("SELECT p.id " + _VISIBLE).fetchall():
        urls.append(url_for("public.photo", photo_id=p["id"], _external=True))
    for r in db.execute("SELECT slug FROM posts WHERE published = 1").fetchall():
        urls.append(url_for("public.post", slug=r["slug"], _external=True))
    for r in db.execute("SELECT DISTINCT t.slug FROM tags t JOIN photo_tags pt ON pt.tag_id = t.id").fetchall():
        urls.append(url_for("public.tag", slug=r["slug"], _external=True))
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    xml += ["<url><loc>%s</loc></url>" % escape(u) for u in urls]
    xml.append("</urlset>")
    return Response("\n".join(xml), mimetype="application/xml")


@bp.route("/blog/feed.xml")
def feed():
    db = get_db()
    site = get_settings()
    posts = db.execute(
        "SELECT * FROM posts WHERE published = 1 "
        "ORDER BY COALESCE(published_at, created_at) DESC, id DESC LIMIT 20"
    ).fetchall()
    items = []
    for p in posts:
        link = url_for("public.post", slug=p["slug"], _external=True)
        items.append(
            "<item><title>%s</title><link>%s</link><guid>%s</guid>"
            "<description>%s</description><pubDate>%s</pubDate></item>"
            % (escape(p["title"]), escape(link), escape(link),
               escape(p["excerpt"] or ""), escape(p["published_at"] or p["created_at"] or ""))
        )
    rss = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
           "<title>%s — Blog</title><link>%s</link><description>%s</description>%s"
           "</channel></rss>"
           % (escape(site.get("site_title", "")), escape(url_for("public.blog", _external=True)),
              escape(site.get("tagline", "")), "".join(items)))
    return Response(rss, mimetype="application/rss+xml")
