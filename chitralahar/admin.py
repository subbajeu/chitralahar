"""Admin panel: photos, categories, blog posts, the about page, and settings."""
import io
import secrets
from pathlib import Path

from flask import (
    Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request,
    send_file, url_for,
)
from werkzeug.security import generate_password_hash

from .auth import login_required
from .db import (
    get_categories, get_db, get_settings, photo_tag_string, set_photo_tags, set_setting,
)
from .images import (
    allowed_file, available_fonts, clear_watermark_cache, delete_misc_file,
    delete_photo_files, process_misc_image, process_png, process_upload,
)
from .utils import (
    excerpt_from, unique_category_slug, unique_slug, unique_subcategory_slug,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_taxonomy(db, category_raw, subcategory_raw):
    """Return a consistent (category_id, subcategory_id) pair.

    A subcategory forces its parent category; invalid ids become None; a photo
    with no category cannot keep a subcategory.
    """
    cat_id = _int_or_none(category_raw)
    sub_id = _int_or_none(subcategory_raw)
    if sub_id is not None:
        row = db.execute(
            "SELECT category_id FROM subcategories WHERE id = ?", (sub_id,)
        ).fetchone()
        if row is None:
            sub_id = None
        else:
            cat_id = row["category_id"]  # parent wins -> always consistent
    if cat_id is not None:
        if db.execute("SELECT 1 FROM categories WHERE id = ?", (cat_id,)).fetchone() is None:
            cat_id = sub_id = None
    else:
        sub_id = None
    return cat_id, sub_id


def _subcat_map(db):
    """Map of category_id -> [{id, name}] for dependent dropdowns."""
    rows = db.execute(
        "SELECT id, category_id, name FROM subcategories "
        "ORDER BY sort_order, name COLLATE NOCASE"
    ).fetchall()
    mapping = {}
    for r in rows:
        mapping.setdefault(r["category_id"], []).append({"id": r["id"], "name": r["name"]})
    return mapping


def _apply_order(db, table, ids):
    """Persist a new sort order. `table` is a trusted literal, never user input."""
    idx = 0
    for raw in ids:
        try:
            rid = int(raw)
        except (TypeError, ValueError):
            continue
        db.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (idx, rid))
        idx += 1
    db.commit()


@bp.route("/")
@login_required
def dashboard():
    db = get_db()
    stats = {
        "photos": db.execute("SELECT COUNT(*) c FROM photos").fetchone()["c"],
        "categories": db.execute("SELECT COUNT(*) c FROM categories").fetchone()["c"],
        "posts": db.execute("SELECT COUNT(*) c FROM posts").fetchone()["c"],
        "drafts": db.execute(
            "SELECT COUNT(*) c FROM posts WHERE published = 0"
        ).fetchone()["c"],
    }
    recent_photos = db.execute(
        "SELECT * FROM photos ORDER BY created_at DESC, id DESC LIMIT 8"
    ).fetchall()
    recent_posts = db.execute(
        "SELECT * FROM posts ORDER BY updated_at DESC LIMIT 5"
    ).fetchall()
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_photos=recent_photos,
        recent_posts=recent_posts,
    )


@bp.route("/preview", methods=["POST"])
@login_required
def preview():
    """Render markdown to HTML for the live editor preview."""
    from .utils import render_markdown

    text = request.json.get("text", "") if request.is_json else ""
    return jsonify({"html": str(render_markdown(text))})


@bp.route("/inline-upload", methods=["POST"])
@login_required
def inline_upload():
    """Upload an image from the blog WYSIWYG editor; returns its URL for embedding."""
    f = request.files.get("image") or request.files.get("file")
    if not f or not f.filename or not allowed_file(f.filename):
        return jsonify({"error": "Unsupported file."}), 400
    try:
        name = process_misc_image(f)
    except ValueError:
        return jsonify({"error": "Could not read image."}), 400
    return jsonify({"url": url_for("static", filename="uploads/misc/" + name)})


# --------------------------- Photos ---------------------------

@bp.route("/photos")
@login_required
def photos():
    db = get_db()
    cat = _int_or_none(request.args.get("cat"))
    sub = _int_or_none(request.args.get("sub"))
    uncat = request.args.get("uncat") is not None
    where, params = "", []
    active = {"cat": None, "sub": None, "uncat": False}
    if uncat:
        where = "WHERE p.category_id IS NULL"
        active["uncat"] = True
    elif sub is not None:
        where, active["sub"] = "WHERE p.subcategory_id = ?", sub
        params.append(sub)
    elif cat is not None:
        where, active["cat"] = "WHERE p.category_id = ?", cat
        params.append(cat)
    items = db.execute(
        f"""SELECT p.*, c.name AS category_name, c.published AS category_published,
                   s.name AS subcategory_name, s.published AS subcategory_published
            FROM photos p
            LEFT JOIN categories c ON c.id = p.category_id
            LEFT JOIN subcategories s ON s.id = p.subcategory_id
            {where}
            ORDER BY p.sort_order, p.created_at DESC, p.id DESC""",
        params,
    ).fetchall()
    browse_cats = db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM photos p WHERE p.category_id = c.id) AS photo_count
           FROM categories c ORDER BY c.sort_order, c.name COLLATE NOCASE"""
    ).fetchall()
    browse_subs = {}
    for srow in db.execute(
        """SELECT s.*, (SELECT COUNT(*) FROM photos p WHERE p.subcategory_id = s.id) AS photo_count
           FROM subcategories s ORDER BY s.sort_order, s.name COLLATE NOCASE"""
    ).fetchall():
        browse_subs.setdefault(srow["category_id"], []).append(srow)
    # The album currently being browsed (so private ones can show their share link).
    active_album = None
    if sub is not None:
        active_album = db.execute("SELECT * FROM subcategories WHERE id = ?", (sub,)).fetchone()
    elif cat is not None:
        active_album = db.execute("SELECT * FROM categories WHERE id = ?", (cat,)).fetchone()
    return render_template(
        "admin/photos.html",
        photos=items,
        categories=get_categories(),
        subcat_map=_subcat_map(db),
        browse_cats=browse_cats,
        browse_subs=browse_subs,
        active=active,
        active_album=active_album,
        total=db.execute("SELECT COUNT(*) c FROM photos").fetchone()["c"],
        uncat_count=db.execute(
            "SELECT COUNT(*) c FROM photos WHERE category_id IS NULL"
        ).fetchone()["c"],
        filtered=bool(where),
    )


@bp.route("/photos/upload", methods=["POST"])
@login_required
def photos_upload():
    db = get_db()
    files = request.files.getlist("photos")
    if not files or all(not f.filename for f in files):
        flash("No files selected.", "error")
        return redirect(url_for("admin.photos"))

    cat_id, sub_id = resolve_taxonomy(
        db, request.form.get("category_id"), request.form.get("subcategory_id")
    )

    tags_raw = (request.form.get("tags") or "").strip()

    # New uploads sort above existing photos.
    base = db.execute(
        "SELECT COALESCE(MIN(sort_order), 0) AS m FROM photos"
    ).fetchone()["m"]
    order = base - 1
    saved = skipped = 0
    for f in files:
        if not f or not f.filename:
            continue
        if not allowed_file(f.filename):
            skipped += 1
            continue
        try:
            info = process_upload(f)
        except ValueError:
            skipped += 1
            continue
        pid = db.execute(
            """INSERT INTO photos
                   (title, filename, thumb_filename, orig_name, orig_filename,
                    width, height, sort_order, category_id, subcategory_id, published)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                "", info["filename"], info["thumb_filename"], info["orig_name"],
                info.get("orig_filename", ""), info["width"], info["height"],
                order, cat_id, sub_id,
            ),
        ).lastrowid
        if tags_raw:
            set_photo_tags(db, pid, tags_raw)
        order -= 1
        saved += 1
    db.commit()

    if saved:
        flash(
            f"Uploaded {saved} photo{'s' if saved != 1 else ''} — "
            "they're live on your site. Click the eye to hide any.",
            "success",
        )
    if skipped:
        flash(
            f"Skipped {skipped} file{'s' if skipped != 1 else ''} "
            "(unsupported format or unreadable).",
            "error",
        )
    return redirect(url_for("admin.photos"))


@bp.route("/photos/<int:photo_id>/edit", methods=["GET", "POST"])
@login_required
def photo_edit(photo_id):
    db = get_db()
    p = db.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if p is None:
        abort(404)
    if request.method == "POST":
        cat_id, sub_id = resolve_taxonomy(
            db, request.form.get("category_id"), request.form.get("subcategory_id")
        )
        db.execute(
            """UPDATE photos SET title=?, caption=?, featured=?, published=?,
                                 category_id=?, subcategory_id=? WHERE id=?""",
            (
                (request.form.get("title") or "").strip(),
                (request.form.get("caption") or "").strip(),
                1 if request.form.get("featured") else 0,
                1 if request.form.get("published") else 0,
                cat_id, sub_id, photo_id,
            ),
        )
        set_photo_tags(db, photo_id, request.form.get("tags"))
        db.commit()
        flash("Photo updated.", "success")
        return redirect(url_for("admin.photos"))
    return render_template(
        "admin/photo_edit.html",
        photo=p,
        categories=get_categories(),
        subcat_map=_subcat_map(db),
        tags=photo_tag_string(db, photo_id),
    )


@bp.route("/photos/<int:photo_id>/featured", methods=["POST"])
@login_required
def photo_toggle_featured(photo_id):
    db = get_db()
    p = db.execute("SELECT featured FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if p is None:
        abort(404)
    new_val = 0 if p["featured"] else 1
    db.execute("UPDATE photos SET featured = ? WHERE id = ?", (new_val, photo_id))
    db.commit()
    return jsonify({"on": new_val})


@bp.route("/photos/<int:photo_id>/published", methods=["POST"])
@login_required
def photo_toggle_published(photo_id):
    db = get_db()
    p = db.execute("SELECT published FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if p is None:
        abort(404)
    new_val = 0 if p["published"] else 1
    db.execute("UPDATE photos SET published = ? WHERE id = ?", (new_val, photo_id))
    db.commit()
    return jsonify({"on": new_val})


@bp.route("/photos/assign", methods=["POST"])
@login_required
def photos_assign():
    """Assign one or more photos to a category/subcategory (drag-drop or bulk)."""
    db = get_db()
    data = request.get_json(silent=True) or {}
    cat_id, sub_id = resolve_taxonomy(
        db, data.get("category_id"), data.get("subcategory_id")
    )
    n = 0
    for raw in data.get("ids") or []:
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        n += db.execute(
            "UPDATE photos SET category_id = ?, subcategory_id = ? WHERE id = ?",
            (cat_id, sub_id, pid),
        ).rowcount
    db.commit()
    label = "Uncategorized"
    if cat_id:
        c = db.execute("SELECT name FROM categories WHERE id = ?", (cat_id,)).fetchone()
        label = c["name"] if c else "Uncategorized"
        if sub_id:
            s = db.execute(
                "SELECT name FROM subcategories WHERE id = ?", (sub_id,)
            ).fetchone()
            if s:
                label += " · " + s["name"]
    return jsonify({"ok": True, "label": label, "count": n})


@bp.route("/photos/<int:photo_id>/delete", methods=["POST"])
@login_required
def photo_delete(photo_id):
    db = get_db()
    p = db.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if p is None:
        abort(404)
    delete_photo_files(p)
    db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    db.commit()
    flash("Photo deleted.", "success")
    return redirect(url_for("admin.photos"))


@bp.route("/photos/reorder", methods=["POST"])
@login_required
def photos_reorder():
    data = request.get_json(silent=True) or {}
    _apply_order(get_db(), "photos", data.get("order", []))
    return jsonify({"ok": True})


# --------------------------- Categories & subcategories ---------------------------

@bp.route("/categories")
@login_required
def categories():
    db = get_db()
    cats = db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM photos p WHERE p.category_id = c.id) AS photo_count,
                  (SELECT COUNT(*) FROM subcategories s WHERE s.category_id = c.id) AS sub_count
           FROM categories c ORDER BY c.sort_order, c.name COLLATE NOCASE"""
    ).fetchall()
    subs = db.execute(
        """SELECT s.*,
                  (SELECT COUNT(*) FROM photos p WHERE p.subcategory_id = s.id) AS photo_count
           FROM subcategories s ORDER BY s.sort_order, s.name COLLATE NOCASE"""
    ).fetchall()
    subs_by_cat = {}
    for s in subs:
        subs_by_cat.setdefault(s["category_id"], []).append(s)
    uncategorized = db.execute(
        "SELECT COUNT(*) c FROM photos WHERE category_id IS NULL"
    ).fetchone()["c"]
    return render_template(
        "admin/categories.html",
        categories=cats,
        subs_by_cat=subs_by_cat,
        uncategorized=uncategorized,
    )


@bp.route("/categories/create", methods=["POST"])
@login_required
def category_create():
    db = get_db()
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("A category name is required.", "error")
        return redirect(url_for("admin.categories"))
    slug = unique_category_slug(db, name)
    order = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 AS m FROM categories"
    ).fetchone()["m"]
    db.execute(
        "INSERT INTO categories(name, slug, description, sort_order) VALUES (?, ?, ?, ?)",
        (name, slug, (request.form.get("description") or "").strip(), order),
    )
    db.commit()
    flash(f"Category “{name}” created.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/categories/<int:cat_id>/edit", methods=["POST"])
@login_required
def category_edit(cat_id):
    db = get_db()
    c = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if c is None:
        abort(404)
    name = (request.form.get("name") or "").strip() or c["name"]
    db.execute(
        "UPDATE categories SET name = ?, description = ? WHERE id = ?",
        (name, (request.form.get("description") or "").strip(), cat_id),
    )
    db.commit()
    flash("Category updated.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/categories/<int:cat_id>/share", methods=["POST"])
@login_required
def category_share(cat_id):
    """Make a category a private shareable album, with or without a passphrase."""
    db = get_db()
    c = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if c is None:
        abort(404)
    private = 1 if request.form.get("private") else 0
    # Keep an existing token (so the link is stable); mint one when first made private.
    token = c["share_token"] or (secrets.token_urlsafe(9) if private else None)
    passkey = c["passkey"]
    if request.form.get("remove_passkey"):
        passkey = ""
    new_pass = (request.form.get("passkey") or "").strip()
    if new_pass:
        passkey = generate_password_hash(new_pass, method="pbkdf2:sha256")
    allow_download = 1 if request.form.get("allow_download") else 0
    db.execute(
        "UPDATE categories SET private = ?, passkey = ?, share_token = ?, allow_download = ? WHERE id = ?",
        (private, passkey, token, allow_download, cat_id),
    )
    db.commit()
    flash("Share settings saved." if private else "“%s” is no longer a private album." % c["name"],
          "success")
    return redirect(url_for("admin.categories"))


@bp.route("/categories/<int:cat_id>/publish", methods=["POST"])
@login_required
def category_toggle_publish(cat_id):
    db = get_db()
    c = db.execute("SELECT published FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if c is None:
        abort(404)
    new_val = 0 if c["published"] else 1
    db.execute("UPDATE categories SET published = ? WHERE id = ?", (new_val, cat_id))
    db.commit()
    return jsonify({"on": new_val})


@bp.route("/categories/<int:cat_id>/delete", methods=["POST"])
@login_required
def category_delete(cat_id):
    db = get_db()
    c = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if c is None:
        abort(404)
    # FK cascade removes subcategories; photos in this category/subcategories
    # have their references set to NULL (the photos themselves are kept).
    db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    db.commit()
    flash(f"Category “{c['name']}” deleted. Its photos are now uncategorized.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/subcategories/create", methods=["POST"])
@login_required
def subcategory_create():
    db = get_db()
    cat_id = _int_or_none(request.form.get("category_id"))
    name = (request.form.get("name") or "").strip()
    if cat_id is None or db.execute(
        "SELECT 1 FROM categories WHERE id = ?", (cat_id,)
    ).fetchone() is None:
        flash("Pick a valid parent category for the subcategory.", "error")
        return redirect(url_for("admin.categories"))
    if not name:
        flash("A subcategory name is required.", "error")
        return redirect(url_for("admin.categories"))
    slug = unique_subcategory_slug(db, cat_id, name)
    order = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 AS m FROM subcategories WHERE category_id = ?",
        (cat_id,),
    ).fetchone()["m"]
    db.execute(
        """INSERT INTO subcategories(category_id, name, slug, description, sort_order)
           VALUES (?, ?, ?, ?, ?)""",
        (cat_id, name, slug, (request.form.get("description") or "").strip(), order),
    )
    db.commit()
    flash(f"Subcategory “{name}” added.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/subcategories/<int:sub_id>/edit", methods=["POST"])
@login_required
def subcategory_edit(sub_id):
    db = get_db()
    s = db.execute("SELECT * FROM subcategories WHERE id = ?", (sub_id,)).fetchone()
    if s is None:
        abort(404)
    name = (request.form.get("name") or "").strip() or s["name"]
    db.execute(
        "UPDATE subcategories SET name = ?, description = ? WHERE id = ?",
        (name, (request.form.get("description") or "").strip(), sub_id),
    )
    db.commit()
    flash("Subcategory updated.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/subcategories/<int:sub_id>/publish", methods=["POST"])
@login_required
def subcategory_toggle_publish(sub_id):
    db = get_db()
    s = db.execute("SELECT published FROM subcategories WHERE id = ?", (sub_id,)).fetchone()
    if s is None:
        abort(404)
    new_val = 0 if s["published"] else 1
    db.execute("UPDATE subcategories SET published = ? WHERE id = ?", (new_val, sub_id))
    db.commit()
    return jsonify({"on": new_val})


@bp.route("/subcategories/<int:sub_id>/delete", methods=["POST"])
@login_required
def subcategory_delete(sub_id):
    db = get_db()
    s = db.execute("SELECT * FROM subcategories WHERE id = ?", (sub_id,)).fetchone()
    if s is None:
        abort(404)
    # Demote photos to the parent category before deleting (the FK then nulls
    # subcategory_id). Photos move up to the parent rather than going uncategorized.
    db.execute(
        "UPDATE photos SET category_id = ? WHERE subcategory_id = ?",
        (s["category_id"], sub_id),
    )
    db.execute("DELETE FROM subcategories WHERE id = ?", (sub_id,))
    db.commit()
    flash(
        f"Subcategory “{s['name']}” deleted. Its photos moved up to the parent category.",
        "success",
    )
    return redirect(url_for("admin.categories"))


@bp.route("/subcategories/<int:sub_id>/share", methods=["POST"])
@login_required
def subcategory_share(sub_id):
    """Make a subcategory a private shareable album, with or without a passphrase."""
    db = get_db()
    s = db.execute("SELECT * FROM subcategories WHERE id = ?", (sub_id,)).fetchone()
    if s is None:
        abort(404)
    private = 1 if request.form.get("private") else 0
    token = s["share_token"] or (secrets.token_urlsafe(9) if private else None)
    passkey = s["passkey"]
    if request.form.get("remove_passkey"):
        passkey = ""
    new_pass = (request.form.get("passkey") or "").strip()
    if new_pass:
        passkey = generate_password_hash(new_pass, method="pbkdf2:sha256")
    allow_download = 1 if request.form.get("allow_download") else 0
    db.execute(
        "UPDATE subcategories SET private = ?, passkey = ?, share_token = ?, allow_download = ? WHERE id = ?",
        (private, passkey, token, allow_download, sub_id),
    )
    db.commit()
    flash("Share settings saved." if private else "“%s” is no longer a private album." % s["name"],
          "success")
    return redirect(url_for("admin.categories"))


@bp.route("/categories/reorder", methods=["POST"])
@login_required
def categories_reorder():
    data = request.get_json(silent=True) or {}
    _apply_order(get_db(), "categories", data.get("order", []))
    return jsonify({"ok": True})


@bp.route("/subcategories/reorder", methods=["POST"])
@login_required
def subcategories_reorder():
    data = request.get_json(silent=True) or {}
    _apply_order(get_db(), "subcategories", data.get("order", []))
    return jsonify({"ok": True})


@bp.route("/subcategories/<int:sub_id>/move", methods=["POST"])
@login_required
def subcategory_move(sub_id):
    """Drag a subcategory onto another category (reparent) or to top level (promote)."""
    db = get_db()
    sub = db.execute("SELECT * FROM subcategories WHERE id = ?", (sub_id,)).fetchone()
    if sub is None:
        abort(404)
    target = str((request.get_json(silent=True) or {}).get("target")
                 or request.form.get("target") or "")

    def done(msg=None, ok=True):
        # Drag-and-drop posts JSON (reload client-side); the Move dropdown posts a
        # form (redirect server-side).
        if request.is_json:
            return jsonify({"ok": ok, "reload": ok})
        if msg:
            flash(msg, "success" if ok else "error")
        return redirect(url_for("admin.categories"))

    if target == "top":  # promote subcategory -> new top-level category
        slug = unique_category_slug(db, sub["name"])
        order = db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS m FROM categories"
        ).fetchone()["m"]
        new_cat = db.execute(
            "INSERT INTO categories(name, slug, description, published, sort_order) "
            "VALUES (?, ?, ?, ?, ?)",
            (sub["name"], slug, sub["description"], sub["published"], order),
        ).lastrowid
        db.execute("UPDATE photos SET category_id = ?, subcategory_id = NULL "
                   "WHERE subcategory_id = ?", (new_cat, sub_id))
        db.execute("DELETE FROM subcategories WHERE id = ?", (sub_id,))
        db.commit()
        return done(f"“{sub['name']}” is now its own top-level category.")

    if target.startswith("cat:"):
        try:
            new_parent = int(target[4:])
        except ValueError:
            return done("Invalid target.", ok=False)
        if new_parent == sub["category_id"]:
            return done()  # dropped on its own category — no-op
        if db.execute("SELECT 1 FROM categories WHERE id = ?", (new_parent,)).fetchone() is None:
            return done("Target category not found.", ok=False)
        slug = unique_subcategory_slug(db, new_parent, sub["name"])
        order = db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS m FROM subcategories WHERE category_id = ?",
            (new_parent,),
        ).fetchone()["m"]
        db.execute("UPDATE subcategories SET category_id = ?, slug = ?, sort_order = ? "
                   "WHERE id = ?", (new_parent, slug, order, sub_id))
        # Keep store-both consistent: the photos' category follows the subcategory.
        db.execute("UPDATE photos SET category_id = ? WHERE subcategory_id = ?",
                   (new_parent, sub_id))
        db.commit()
        return done(f"“{sub['name']}” moved.")

    return done("Invalid target.", ok=False)


@bp.route("/categories/<int:cat_id>/move", methods=["POST"])
@login_required
def category_move(cat_id):
    """Demote a category to a subcategory of another category (via the Edit form)."""
    db = get_db()
    cat = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if cat is None:
        abort(404)
    target = str((request.get_json(silent=True) or {}).get("target")
                 or request.form.get("target") or "")

    def done(msg=None, ok=True):
        if request.is_json:
            return jsonify({"ok": ok, "reload": ok, "error": (None if ok else msg)})
        if msg:
            flash(msg, "success" if ok else "error")
        return redirect(url_for("admin.categories"))

    if not target or target == "top":
        return done()  # already top-level
    if not target.startswith("cat:"):
        return done("Invalid target.", ok=False)
    try:
        new_parent = int(target[4:])
    except ValueError:
        return done("Invalid target.", ok=False)
    if new_parent == cat_id:
        return done("A category cannot be nested under itself.", ok=False)
    if db.execute("SELECT 1 FROM categories WHERE id = ?", (new_parent,)).fetchone() is None:
        return done("Target category not found.", ok=False)
    if db.execute("SELECT 1 FROM subcategories WHERE category_id = ?", (cat_id,)).fetchone():
        return done(f"“{cat['name']}” has subcategories — move or delete them first.", ok=False)
    slug = unique_subcategory_slug(db, new_parent, cat["name"])
    order = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 AS m FROM subcategories WHERE category_id = ?",
        (new_parent,),
    ).fetchone()["m"]
    new_sub = db.execute(
        "INSERT INTO subcategories(category_id, name, slug, description, published, sort_order) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (new_parent, cat["name"], slug, cat["description"], cat["published"], order),
    ).lastrowid
    db.execute("UPDATE photos SET category_id = ?, subcategory_id = ? WHERE category_id = ?",
               (new_parent, new_sub, cat_id))
    db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    db.commit()
    return done(f"“{cat['name']}” is now a subcategory.")


# --------------------------- Navigation menu ---------------------------

MENU_TYPES = {"home", "blog", "about", "contact", "category", "subcategory", "url"}
_BUILTIN_LABELS = {"home": "Work", "blog": "Blog", "about": "About", "contact": "Contact"}


def _menu_desc(m):
    lt = m["link_type"]
    if lt == "category":
        return "Category · " + (m["cat_name"] or "—")
    if lt == "subcategory":
        return "Subcategory · " + (m["sub_name"] or "—")
    if lt == "url":
        return m["url"] or "URL"
    return _BUILTIN_LABELS.get(lt, lt)


def _safe_external_url(value):
    """Allow only http(s)/mailto/tel or site-relative URLs; reject javascript:,
    data:, etc. A bare domain is upgraded to https://. Returns "" if unsafe/empty."""
    v = (value or "").strip()
    if not v:
        return ""
    low = v.lower()
    if low.startswith(("http://", "https://", "mailto:", "tel:")) or v.startswith("/"):
        return v
    if ":" in v.split("/", 1)[0]:
        return ""  # an unapproved scheme (javascript:, data:, …)
    return "https://" + v  # bare domain → assume https


def _menu_payload(db):
    """Validate a menu form into a stored payload, or return (None, error)."""
    lt = (request.form.get("link_type") or "").strip()
    if lt not in MENU_TYPES:
        return None, "Choose what this menu item links to."
    cat_id = sub_id = None
    url = ""
    if lt == "category":
        cat_id, _ = resolve_taxonomy(db, request.form.get("category_id"), None)
        if cat_id is None:
            return None, "Pick a category for this menu item."
    elif lt == "subcategory":
        cat_id, sub_id = resolve_taxonomy(
            db, request.form.get("category_id"), request.form.get("subcategory_id")
        )
        if sub_id is None:
            return None, "Pick a subcategory for this menu item."
    elif lt == "url":
        url = _safe_external_url(request.form.get("url"))
        if not url:
            return None, "Enter a valid http(s), mailto:, tel: or /relative URL."
    label = (request.form.get("label") or "").strip()
    if not label:
        if lt in _BUILTIN_LABELS:
            label = _BUILTIN_LABELS[lt]
        elif cat_id and lt == "category":
            r = db.execute("SELECT name FROM categories WHERE id=?", (cat_id,)).fetchone()
            label = r["name"] if r else "Category"
        elif sub_id:
            r = db.execute("SELECT name FROM subcategories WHERE id=?", (sub_id,)).fetchone()
            label = r["name"] if r else "Subcategory"
        else:
            label = url or "Link"
    return {"label": label, "link_type": lt, "category_id": cat_id,
            "subcategory_id": sub_id, "url": url}, None


@bp.route("/menu")
@login_required
def menu():
    db = get_db()
    items = db.execute(
        """SELECT m.*, c.name AS cat_name, s.name AS sub_name
           FROM menu_items m
           LEFT JOIN categories c ON c.id = m.category_id
           LEFT JOIN subcategories s ON s.id = m.subcategory_id
           ORDER BY m.sort_order, m.id"""
    ).fetchall()
    tops = [i for i in items if i["parent_id"] is None]
    children = {}
    for i in items:
        if i["parent_id"] is not None:
            children.setdefault(i["parent_id"], []).append(i)
    descs = {i["id"]: _menu_desc(i) for i in items}
    return render_template(
        "admin/menu.html",
        tops=tops, children=children, descs=descs,
        categories=get_categories(), subcat_map=_subcat_map(db),
    )


@bp.route("/menu/create", methods=["POST"])
@login_required
def menu_create():
    db = get_db()
    payload, err = _menu_payload(db)
    if err:
        flash(err, "error")
        return redirect(url_for("admin.menu"))
    parent_id = _int_or_none(request.form.get("parent_id"))
    if parent_id is not None:
        par = db.execute(
            "SELECT parent_id FROM menu_items WHERE id=?", (parent_id,)
        ).fetchone()
        if par is None or par["parent_id"] is not None:
            parent_id = None  # only one level of nesting
    order = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 AS m FROM menu_items WHERE parent_id IS ?",
        (parent_id,),
    ).fetchone()["m"]
    db.execute(
        """INSERT INTO menu_items(parent_id, label, link_type, category_id,
                                  subcategory_id, url, sort_order)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (parent_id, payload["label"], payload["link_type"], payload["category_id"],
         payload["subcategory_id"], payload["url"], order),
    )
    db.commit()
    flash("Menu item added.", "success")
    return redirect(url_for("admin.menu"))


@bp.route("/menu/<int:item_id>/edit", methods=["POST"])
@login_required
def menu_edit(item_id):
    db = get_db()
    if db.execute("SELECT 1 FROM menu_items WHERE id=?", (item_id,)).fetchone() is None:
        abort(404)
    payload, err = _menu_payload(db)
    if err:
        flash(err, "error")
        return redirect(url_for("admin.menu"))
    db.execute(
        """UPDATE menu_items SET label=?, link_type=?, category_id=?,
                                 subcategory_id=?, url=? WHERE id=?""",
        (payload["label"], payload["link_type"], payload["category_id"],
         payload["subcategory_id"], payload["url"], item_id),
    )
    db.commit()
    flash("Menu item updated.", "success")
    return redirect(url_for("admin.menu"))


@bp.route("/menu/<int:item_id>/publish", methods=["POST"])
@login_required
def menu_toggle_publish(item_id):
    db = get_db()
    it = db.execute("SELECT published FROM menu_items WHERE id=?", (item_id,)).fetchone()
    if it is None:
        abort(404)
    new_val = 0 if it["published"] else 1
    db.execute("UPDATE menu_items SET published=? WHERE id=?", (new_val, item_id))
    db.commit()
    return jsonify({"on": new_val})


@bp.route("/menu/<int:item_id>/delete", methods=["POST"])
@login_required
def menu_delete(item_id):
    db = get_db()
    it = db.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
    if it is None:
        abort(404)
    db.execute("DELETE FROM menu_items WHERE id=?", (item_id,))  # children cascade
    db.commit()
    flash("Menu item deleted.", "success")
    return redirect(url_for("admin.menu"))


@bp.route("/menu/reorder", methods=["POST"])
@login_required
def menu_reorder():
    data = request.get_json(silent=True) or {}
    _apply_order(get_db(), "menu_items", data.get("order", []))
    return jsonify({"ok": True})


@bp.route("/menu/<int:item_id>/move", methods=["POST"])
@login_required
def menu_move(item_id):
    """Reparent a menu item: drag onto another item (child) or to top level."""
    db = get_db()
    it = db.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()
    if it is None:
        abort(404)
    raw = (request.get_json(silent=True) or {}).get("parent")
    if raw is None:
        raw = request.form.get("parent", "")
    raw = str(raw)

    new_parent = None
    if raw not in ("", "top", "0", "none"):
        try:
            candidate = int(raw)
        except ValueError:
            candidate = None
        if candidate and candidate != item_id:
            par = db.execute(
                "SELECT parent_id FROM menu_items WHERE id = ?", (candidate,)
            ).fetchone()
            if par is not None and par["parent_id"] is None:  # nest only under a top item
                new_parent = candidate

    # An item with its own children cannot become a child (keep one level).
    if new_parent is not None and db.execute(
        "SELECT 1 FROM menu_items WHERE parent_id = ?", (item_id,)
    ).fetchone():
        msg = "Move this item's sub-items out before nesting it."
        if request.is_json:
            return jsonify({"ok": False, "error": msg}), 400
        flash(msg, "error")
        return redirect(url_for("admin.menu"))

    order = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 AS m FROM menu_items WHERE parent_id IS ?",
        (new_parent,),
    ).fetchone()["m"]
    db.execute("UPDATE menu_items SET parent_id = ?, sort_order = ? WHERE id = ?",
               (new_parent, order, item_id))
    db.commit()
    if request.is_json:
        return jsonify({"ok": True, "reload": True})
    flash("Menu item moved.", "success")
    return redirect(url_for("admin.menu"))


# --------------------------- Blog posts ---------------------------

@bp.route("/posts")
@login_required
def posts():
    items = get_db().execute(
        "SELECT * FROM posts ORDER BY updated_at DESC, id DESC"
    ).fetchall()
    return render_template("admin/posts.html", posts=items)


@bp.route("/posts/new", methods=["GET", "POST"])
@login_required
def post_new():
    db = get_db()
    if request.method == "POST":
        return _save_post(db, None)
    return render_template("admin/post_edit.html", post=None)


@bp.route("/posts/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def post_edit(post_id):
    db = get_db()
    p = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if p is None:
        abort(404)
    if request.method == "POST":
        return _save_post(db, p)
    return render_template("admin/post_edit.html", post=p)


def _save_post(db, existing):
    title = (request.form.get("title") or "").strip() or "Untitled"
    body = request.form.get("body") or ""
    excerpt = (request.form.get("excerpt") or "").strip() or excerpt_from(body)
    published = 1 if request.form.get("published") else 0
    slug_src = (request.form.get("slug") or "").strip() or title
    post_id = existing["id"] if existing else None
    slug = unique_slug(db, slug_src, "posts", exclude_id=post_id)

    cover = existing["cover_filename"] if existing else None
    if request.form.get("remove_cover") and cover:
        delete_misc_file(cover)
        cover = None
    upload = request.files.get("cover")
    if upload and upload.filename:
        if allowed_file(upload.filename):
            try:
                new_cover = process_misc_image(upload)
                if cover:
                    delete_misc_file(cover)
                cover = new_cover
            except ValueError:
                flash("Cover image could not be processed.", "error")
        else:
            flash("Cover must be an image file.", "error")

    if existing:
        if published and not existing["published"]:
            db.execute(
                "UPDATE posts SET published_at = datetime('now') WHERE id = ?",
                (post_id,),
            )
        db.execute(
            """UPDATE posts SET title=?, slug=?, excerpt=?, body=?, cover_filename=?,
                                published=?, updated_at=datetime('now')
               WHERE id=?""",
            (title, slug, excerpt, body, cover, published, post_id),
        )
        flash("Post saved.", "success")
    else:
        db.execute(
            """INSERT INTO posts
                   (title, slug, excerpt, body, cover_filename, published, published_at)
               VALUES (?, ?, ?, ?, ?, ?,
                       CASE WHEN ? = 1 THEN datetime('now') ELSE NULL END)""",
            (title, slug, excerpt, body, cover, published, published),
        )
        flash("Post created.", "success")
    db.commit()
    return redirect(url_for("admin.posts"))


@bp.route("/posts/<int:post_id>/delete", methods=["POST"])
@login_required
def post_delete(post_id):
    db = get_db()
    p = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if p is None:
        abort(404)
    if p["cover_filename"]:
        delete_misc_file(p["cover_filename"])
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.commit()
    flash("Post deleted.", "success")
    return redirect(url_for("admin.posts"))


# --------------------------- Editable pages (About, Contact) ---------------------------

def _save_page(db, slug, default_title):
    page = db.execute("SELECT * FROM pages WHERE slug = ?", (slug,)).fetchone()
    title = (request.form.get("title") or default_title).strip()
    body = request.form.get("body") or ""
    image = page["image_filename"] if page else None
    if request.form.get("remove_image") and image:
        delete_misc_file(image)
        image = None
    upload = request.files.get("image")
    if upload and upload.filename:
        if allowed_file(upload.filename):
            try:
                new_img = process_misc_image(upload)
                if image:
                    delete_misc_file(image)
                image = new_img
            except ValueError:
                flash("Image could not be processed.", "error")
        else:
            flash("That must be an image file.", "error")
    db.execute(
        """INSERT INTO pages(slug, title, body, image_filename) VALUES (?, ?, ?, ?)
           ON CONFLICT(slug) DO UPDATE SET title=excluded.title, body=excluded.body,
                                           image_filename=excluded.image_filename,
                                           updated_at=datetime('now')""",
        (slug, title, body, image),
    )
    db.commit()


@bp.route("/about", methods=["GET", "POST"])
@login_required
def about_edit():
    db = get_db()
    if request.method == "POST":
        _save_page(db, "about", "About")
        flash("About page saved.", "success")
        return redirect(url_for("admin.about_edit"))
    page = db.execute("SELECT * FROM pages WHERE slug = 'about'").fetchone()
    return render_template("admin/page_edit.html", page=page, heading="About page",
                           action=url_for("admin.about_edit"),
                           view_url=url_for("public.about"), default_title="About")


@bp.route("/contact", methods=["GET", "POST"])
@login_required
def contact_edit():
    db = get_db()
    if request.method == "POST":
        _save_page(db, "contact", "Contact")
        flash("Contact page saved.", "success")
        return redirect(url_for("admin.contact_edit"))
    page = db.execute("SELECT * FROM pages WHERE slug = 'contact'").fetchone()
    return render_template("admin/page_edit.html", page=page, heading="Contact page",
                           action=url_for("admin.contact_edit"),
                           view_url=url_for("public.contact"), default_title="Contact")


# --------------------------- Settings & templates ---------------------------

# home_heading / home_intro / home_show / home_category / home_hero are owned by
# the Home page editor; logo & favicon are handled as uploads below.
SETTING_KEYS = [
    "site_title", "tagline", "author_name",
    "footer_text", "footer_copyright", "instagram", "twitter", "facebook", "email",
    "watermark_text", "watermark_position", "watermark_opacity",
]


def _save_image_setting(key, max_edge, png=True):
    """Handle one upload/remove image field on a settings form."""
    f = request.files.get(key)
    if f and f.filename:
        if not allowed_file(f.filename):
            flash("Unsupported image format for %s." % key.replace("_", " "), "error")
            return
        try:
            name = process_png(f, max_edge=max_edge) if png else process_misc_image(f, max_edge=max_edge)
        except ValueError:
            flash("Could not read the %s image." % key.replace("_", " "), "error")
            return
        old = get_settings().get(key)
        set_setting(key, name)
        if old and old != name:
            delete_misc_file(old)
    elif request.form.get("remove_" + key):
        old = get_settings().get(key)
        set_setting(key, "")
        if old:
            delete_misc_file(old)


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        social_keys = {"instagram", "twitter", "facebook"}
        for key in SETTING_KEYS:
            val = (request.form.get(key) or "").strip()
            if key in social_keys:
                val = _safe_external_url(val)  # block javascript:/data: in href output
            set_setting(key, val)
        set_setting("watermark_enabled", "1" if request.form.get("watermark_enabled") else "")
        # Validated watermark choices.
        wt = (request.form.get("watermark_type") or "text").strip()
        set_setting("watermark_type", wt if wt in ("text", "image") else "text")
        try:
            fsz = max(10, min(800, int(request.form.get("watermark_font_size") or 100)))
        except (TypeError, ValueError):
            fsz = 100
        set_setting("watermark_font_size", str(fsz))
        col = (request.form.get("watermark_color") or "#ffffff").strip()
        ok_hex = len(col) == 7 and col[0] == "#" and all(ch in "0123456789abcdefABCDEF" for ch in col[1:])
        set_setting("watermark_color", col if ok_hex else "#ffffff")
        valid_fonts = {fn for _, fn in available_fonts()}
        wf = (request.form.get("watermark_font") or "").strip()
        set_setting("watermark_font", wf if wf in valid_fonts else "")
        try:
            scale = max(3, min(100, int(request.form.get("watermark_scale") or 18)))
        except (TypeError, ValueError):
            scale = 18
        set_setting("watermark_scale", str(scale))
        _save_image_setting("logo", 600)
        _save_image_setting("favicon", 180)
        _save_image_setting("watermark_image", 1000)
        clear_watermark_cache()  # regenerate with the new settings on next view
        flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html", values=get_settings(), fonts=available_fonts())


def _watermark_preview_base():
    """A representative image to preview the watermark on: the most recent photo's
    display image if there is one, otherwise a quick gradient."""
    from PIL import Image
    db = get_db()
    row = db.execute("SELECT filename FROM photos ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        p = Path(current_app.config["UPLOAD_FOLDER"]) / "photos" / row["filename"]
        if p.exists():
            try:
                img = Image.open(p).convert("RGBA")
                if img.width > 1100:
                    img = img.resize((1100, max(1, int(img.height * 1100 / img.width))))
                return img
            except Exception:  # noqa: BLE001
                pass
    small = Image.new("RGB", (16, 10))
    px = small.load()
    for y in range(10):
        for x in range(16):
            px[x, y] = (70 + x * 8, 80 + y * 7, 120)
    return small.resize((1100, 700)).convert("RGBA")


@bp.route("/watermark-preview")
@login_required
def watermark_preview():
    """Render the watermark from the live form params onto a sample image, so the
    Settings page can show how it will look. (Image watermark uses the saved file.)"""
    from .images import _apply_watermark
    saved = get_settings()
    valid_fonts = {fn for _, fn in available_fonts()}
    font = (request.args.get("font") or "").strip()
    s = {
        "watermark_type": request.args.get("type") or "text",
        "watermark_text": (request.args.get("text") or "").strip() or saved.get("site_title") or "©",
        "watermark_font": font if font in valid_fonts else "",
        "watermark_font_size": request.args.get("size") or "100",
        "watermark_color": request.args.get("color") or "#ffffff",
        "watermark_position": request.args.get("position") or "br",
        "watermark_opacity": request.args.get("opacity") or "35",
        "watermark_scale": request.args.get("scale") or "18",
        "watermark_image": saved.get("watermark_image", ""),
        "site_title": saved.get("site_title", ""),
    }
    out = _apply_watermark(_watermark_preview_base(), s).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=82)
    buf.seek(0)
    resp = send_file(buf, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/home", methods=["GET", "POST"])
@login_required
def home_settings():
    """Control what the public home page shows."""
    if request.method == "POST":
        set_setting("home_heading", (request.form.get("home_heading") or "").strip())
        set_setting("home_intro", (request.form.get("home_intro") or "").strip())
        show = (request.form.get("home_show") or "all").strip()
        if show not in ("all", "featured", "category"):
            show = "all"
        set_setting("home_show", show)
        set_setting("home_category",
                    (request.form.get("home_category") or "").strip() if show == "category" else "")
        _save_image_setting("home_hero", 2200, png=False)
        flash("Home page saved.", "success")
        return redirect(url_for("admin.home_settings"))
    db = get_db()
    return render_template(
        "admin/home.html",
        values=get_settings(),
        categories=get_categories(),
        featured_count=db.execute(
            "SELECT COUNT(*) c FROM photos WHERE featured = 1 AND published = 1"
        ).fetchone()["c"],
    )


@bp.route("/templates", methods=["GET", "POST"])
@login_required
def templates():
    from .db import TEMPLATES

    if request.method == "POST":
        choice = (request.form.get("template") or "").strip()
        if choice in TEMPLATES:
            set_setting("template", choice)
            flash(f"Template set to “{TEMPLATES[choice]['name']}”.", "success")
        else:
            flash("Unknown template.", "error")
        return redirect(url_for("admin.templates"))
    return render_template(
        "admin/templates.html",
        templates=TEMPLATES,
        current=get_settings().get("template", "minimal"),
    )
