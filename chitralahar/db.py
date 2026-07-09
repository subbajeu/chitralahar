"""SQLite database access, initialization, and lightweight migrations."""
import sqlite3
from pathlib import Path

import click
from flask import current_app, g

DEFAULT_SETTINGS = {
    "site_title": "Chitralahar",
    "tagline": "Photography",
    "author_name": "",
    "home_heading": "Selected Work",
    "footer_text": "",
    "footer_copyright": "",   # the © line; blank → "© <year> <name>"
    "instagram": "",
    "twitter": "",
    "facebook": "",
    "email": "",
    "logo": "",            # header wordmark image (uploads/misc); falls back to site_title
    "favicon": "",         # browser tab icon (uploads/misc)
    "home_intro": "",      # optional intro paragraph under the home heading
    "home_hero": "",       # optional hero banner image on the home page
    "home_show": "all",    # which photos the home gallery shows: all | featured | category
    "home_category": "",   # category id when home_show == "category"
    "watermark_enabled": "",     # "1" overlays a watermark on PUBLIC images (originals stay clean)
    "watermark_type": "text",    # text | image
    "watermark_text": "",        # blank → falls back to the site title
    "watermark_font": "",         # filename in static/fonts/ ("" = built-in default)
    "watermark_font_size": "100", # text size in px (calibrated to display width; scales per image)
    "watermark_color": "#ffffff", # text colour (hex)
    "watermark_image": "",        # uploaded watermark/logo image (in uploads/misc)
    "watermark_scale": "18",     # image-watermark width as a % of the photo width
    "watermark_position": "br",  # br | bl | tr | tl | center | tiled
    "watermark_opacity": "35",   # percent
    "show_exif": "",             # "1" shows camera/EXIF details on public photo pages
    "template": "minimal",
}

# Built-in public templates (id -> label + blurb). Used by the admin chooser and
# validated server-side so only known templates can be applied.
TEMPLATES = {
    "minimal": {"name": "Minimal", "blurb": "Bright, airy masonry. Photos as heroes."},
    "noir": {"name": "Noir", "blurb": "Deep charcoal canvas. Cinematic and bold."},
    "grid": {"name": "Grid", "blurb": "Uniform square grid. Crisp and orderly."},
    "frame": {"name": "Frame", "blurb": "Gallery-wall matting around each image."},
    "editorial": {"name": "Editorial", "blurb": "Serif-led, magazine-style features."},
    "slider": {"name": "Slider", "blurb": "A full-width slideshow of your featured (★) photos atop the home page."},
}


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        # timeout + WAL + busy_timeout let multiple gunicorn workers write without
        # raising "database is locked"; WAL is persisted in the DB header.
        conn = sqlite3.connect(current_app.config["DATABASE"], timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA synchronous = NORMAL")
        g.db = conn
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    schema_path = Path(current_app.root_path) / "schema.sql"
    db.executescript(schema_path.read_text(encoding="utf-8"))
    _migrate(db)
    _seed_defaults(db)


def _migrate(db):
    """Idempotent, non-destructive upgrades for databases created by older versions."""
    cols = {r["name"] for r in db.execute("PRAGMA table_info(photos)").fetchall()}
    if not cols:
        return

    if "published" not in cols:
        db.execute("ALTER TABLE photos ADD COLUMN published INTEGER NOT NULL DEFAULT 1")
    if "category_id" not in cols:
        db.execute(
            "ALTER TABLE photos ADD COLUMN category_id INTEGER "
            "REFERENCES categories(id) ON DELETE SET NULL"
        )
    if "subcategory_id" not in cols:
        db.execute(
            "ALTER TABLE photos ADD COLUMN subcategory_id INTEGER "
            "REFERENCES subcategories(id) ON DELETE SET NULL"
        )
    if "orig_filename" not in cols:
        db.execute("ALTER TABLE photos ADD COLUMN orig_filename TEXT NOT NULL DEFAULT ''")
    if "exif" not in cols:
        db.execute("ALTER TABLE photos ADD COLUMN exif TEXT NOT NULL DEFAULT ''")

    # Fold any legacy free-text `category` values into real category rows.
    if "category" in cols:
        from .utils import unique_category_slug

        rows = db.execute(
            "SELECT DISTINCT category FROM photos "
            "WHERE TRIM(category) <> '' AND category_id IS NULL"
        ).fetchall()
        for r in rows:
            name = (r["category"] or "").strip()
            if not name:
                continue
            existing = db.execute(
                "SELECT id FROM categories WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if existing:
                cat_id = existing["id"]
            else:
                slug = unique_category_slug(db, name)
                cat_id = db.execute(
                    "INSERT INTO categories(name, slug) VALUES (?, ?)", (name, slug)
                ).lastrowid
            # Clear the legacy text after backfilling so this can never re-link a
            # row that the admin later deliberately un-categorizes.
            db.execute(
                "UPDATE photos SET category_id = ?, category = '' "
                "WHERE category = ? AND category_id IS NULL",
                (cat_id, r["category"]),
            )

    # Indexes on the (now guaranteed-to-exist) photo taxonomy columns.
    db.execute("CREATE INDEX IF NOT EXISTS idx_photos_cat ON photos(category_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_photos_subcat ON photos(subcategory_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_photos_pub ON photos(published)")

    # Private (client) galleries: columns on categories added by later versions.
    cat_cols = {r["name"] for r in db.execute("PRAGMA table_info(categories)").fetchall()}
    if cat_cols:
        if "private" not in cat_cols:
            db.execute("ALTER TABLE categories ADD COLUMN private INTEGER NOT NULL DEFAULT 0")
        if "passkey" not in cat_cols:
            db.execute("ALTER TABLE categories ADD COLUMN passkey TEXT NOT NULL DEFAULT ''")
        if "share_token" not in cat_cols:
            db.execute("ALTER TABLE categories ADD COLUMN share_token TEXT")
        if "allow_download" not in cat_cols:
            db.execute("ALTER TABLE categories ADD COLUMN allow_download INTEGER NOT NULL DEFAULT 0")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cat_token ON categories(share_token)")

    # Private albums on subcategories too.
    sub_cols = {r["name"] for r in db.execute("PRAGMA table_info(subcategories)").fetchall()}
    if sub_cols:
        if "private" not in sub_cols:
            db.execute("ALTER TABLE subcategories ADD COLUMN private INTEGER NOT NULL DEFAULT 0")
        if "passkey" not in sub_cols:
            db.execute("ALTER TABLE subcategories ADD COLUMN passkey TEXT NOT NULL DEFAULT ''")
        if "share_token" not in sub_cols:
            db.execute("ALTER TABLE subcategories ADD COLUMN share_token TEXT")
        if "allow_download" not in sub_cols:
            db.execute("ALTER TABLE subcategories ADD COLUMN allow_download INTEGER NOT NULL DEFAULT 0")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_subcat_token ON subcategories(share_token)")
    db.commit()


def _seed_defaults(db):
    for key, value in DEFAULT_SETTINGS.items():
        db.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value)
        )
    for slug, title, body in [
        ("about", "About", "Tell your story here. Edit this from the admin panel under **About**."),
        ("contact", "Contact", "How people can reach you. Edit this under **Contact** in admin."),
    ]:
        db.execute("INSERT OR IGNORE INTO pages(slug, title, body) VALUES (?, ?, ?)",
                   (slug, title, body))

    # Seed the navigation menu once (mirrors the previous hard-coded nav + Contact).
    # Guarded by a sentinel so it never reappears if the owner deletes every item.
    if db.execute("SELECT 1 FROM settings WHERE key = 'menu_seeded'").fetchone() is None:
        for i, (label, lt) in enumerate(
            [("Work", "home"), ("Blog", "blog"), ("About", "about"), ("Contact", "contact")]
        ):
            db.execute(
                "INSERT INTO menu_items(label, link_type, sort_order) VALUES (?, ?, ?)",
                (label, lt, i),
            )
        db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('menu_seeded', '1')")
    elif db.execute("SELECT 1 FROM settings WHERE key = 'contact_seeded'").fetchone() is None:
        # Existing site that predates Contact: add one Contact item, once.
        if db.execute("SELECT 1 FROM menu_items WHERE link_type = 'contact'").fetchone() is None:
            order = db.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 AS m FROM menu_items WHERE parent_id IS NULL"
            ).fetchone()["m"]
            db.execute(
                "INSERT INTO menu_items(label, link_type, sort_order) VALUES ('Contact', 'contact', ?)",
                (order,),
            )
        db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('contact_seeded', '1')")

    # One-time: pages (About/Contact) move from Markdown to HTML for the WYSIWYG
    # editor; convert existing bodies so their formatting carries over.
    if db.execute("SELECT 1 FROM settings WHERE key = 'pages_html'").fetchone() is None:
        from .utils import render_markdown
        for pg in db.execute("SELECT slug, body FROM pages").fetchall():
            db.execute("UPDATE pages SET body = ? WHERE slug = ?",
                       (str(render_markdown(pg["body"])), pg["slug"]))
        db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('pages_html', '1')")
    db.commit()


# --------------------------- Settings ---------------------------

def get_setting(key, default=""):
    row = get_db().execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else default


def get_settings() -> dict:
    rows = get_db().execute("SELECT key, value FROM settings").fetchall()
    data = dict(DEFAULT_SETTINGS)
    data.update({r["key"]: r["value"] for r in rows})
    if data.get("template") not in TEMPLATES:
        data["template"] = "minimal"
    return data


def set_setting(key, value):
    db = get_db()
    db.execute(
        """INSERT INTO settings(key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (key, value),
    )
    db.commit()


# --------------------------- Taxonomy helpers ---------------------------

def get_categories(published_only=False):
    q = "SELECT * FROM categories"
    if published_only:
        q += " WHERE published = 1"
    q += " ORDER BY sort_order, name COLLATE NOCASE"
    return get_db().execute(q).fetchall()


def get_subcategories(category_id=None, published_only=False):
    clauses, params = [], []
    if category_id is not None:
        clauses.append("category_id = ?")
        params.append(category_id)
    if published_only:
        clauses.append("published = 1")
    q = "SELECT * FROM subcategories"
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY sort_order, name COLLATE NOCASE"
    return get_db().execute(q, params).fetchall()


# --------------------------- Tags ---------------------------

def photo_tags(db, photo_id):
    """(name, slug) rows for a photo's tags, alphabetical."""
    return db.execute(
        "SELECT t.name, t.slug FROM tags t JOIN photo_tags pt ON pt.tag_id = t.id "
        "WHERE pt.photo_id = ? ORDER BY t.name COLLATE NOCASE",
        (photo_id,),
    ).fetchall()


def photo_tag_string(db, photo_id):
    """A photo's tags as a single comma-separated string (for the edit field)."""
    return ", ".join(r["name"] for r in photo_tags(db, photo_id))


def set_photo_tags(db, photo_id, raw):
    """Replace a photo's tags from a comma-separated string; upserts tag rows and
    prunes any tag left with no photos. Does not commit."""
    from .utils import make_slug

    wanted, seen = [], set()
    for part in (raw or "").replace(";", ",").replace("\n", ",").split(","):
        name = part.strip()
        if not name:
            continue
        slug = make_slug(name)
        if slug in seen:
            continue
        seen.add(slug)
        wanted.append((name, slug))

    db.execute("DELETE FROM photo_tags WHERE photo_id = ?", (photo_id,))
    for name, slug in wanted:
        row = db.execute("SELECT id FROM tags WHERE slug = ?", (slug,)).fetchone()
        tag_id = row["id"] if row else db.execute(
            "INSERT INTO tags(name, slug) VALUES (?, ?)", (name, slug)
        ).lastrowid
        db.execute(
            "INSERT OR IGNORE INTO photo_tags(photo_id, tag_id) VALUES (?, ?)",
            (photo_id, tag_id),
        )
    db.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM photo_tags)")


def resolve_tag(db, slug):
    return db.execute("SELECT * FROM tags WHERE slug = ?", (slug,)).fetchone()


@click.command("init-db")
def init_db_command():
    """Create database tables and seed defaults."""
    init_db()
    click.echo("Initialized the Chitralahar database.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
