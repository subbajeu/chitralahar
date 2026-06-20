-- Chitralahar CMS database schema

PRAGMA foreign_keys = ON;

-- Admin users
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Categories (top level of the taxonomy)
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    slug        TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    published   INTEGER NOT NULL DEFAULT 1,
    private     INTEGER NOT NULL DEFAULT 0,   -- client gallery: hidden from public site
    passkey     TEXT NOT NULL DEFAULT '',     -- optional pbkdf2 hash to view a private gallery
    share_token TEXT,                          -- random token for the private /private/<token> URL
    allow_download INTEGER NOT NULL DEFAULT 0, -- let viewers download the whole album as a ZIP
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Subcategories (each belongs to exactly one category)
CREATE TABLE IF NOT EXISTS subcategories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    published   INTEGER NOT NULL DEFAULT 1,
    private     INTEGER NOT NULL DEFAULT 0,   -- client album: hidden from public site
    passkey     TEXT NOT NULL DEFAULT '',     -- optional pbkdf2 hash to view it
    share_token TEXT,                          -- random token for /private/<token>
    allow_download INTEGER NOT NULL DEFAULT 0, -- let viewers download the whole album as a ZIP
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (category_id, slug)
);

-- Navigation menu items (the public header menu). A two-level structure:
-- top-level items (parent_id NULL) may have children that render as a dropdown.
-- An item links to a built-in section, a category, a subcategory, or a URL.
CREATE TABLE IF NOT EXISTS menu_items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id      INTEGER REFERENCES menu_items(id) ON DELETE CASCADE,
    label          TEXT NOT NULL,
    link_type      TEXT NOT NULL DEFAULT 'url',  -- home|blog|about|category|subcategory|url
    category_id    INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    subcategory_id INTEGER REFERENCES subcategories(id) ON DELETE CASCADE,
    url            TEXT NOT NULL DEFAULT '',
    published      INTEGER NOT NULL DEFAULT 1,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Portfolio photos. A photo may sit directly in a category, in a subcategory
-- (which implies its parent category), or be uncategorised. Deleting a category
-- or subcategory sets the photo's references to NULL (the photo is kept).
CREATE TABLE IF NOT EXISTS photos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL DEFAULT '',
    caption        TEXT NOT NULL DEFAULT '',
    filename       TEXT NOT NULL,            -- display-size image (~2200px)
    thumb_filename TEXT NOT NULL,            -- gallery thumbnail
    orig_name      TEXT NOT NULL DEFAULT '', -- original upload filename (as uploaded)
    orig_filename  TEXT NOT NULL DEFAULT '', -- kept full-resolution original on disk
    width          INTEGER NOT NULL DEFAULT 0,
    height         INTEGER NOT NULL DEFAULT 0,
    featured       INTEGER NOT NULL DEFAULT 0,
    published      INTEGER NOT NULL DEFAULT 1,
    category_id    INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    subcategory_id INTEGER REFERENCES subcategories(id) ON DELETE SET NULL,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Free-form tags, many-to-many with photos.
CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS photo_tags (
    photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (photo_id, tag_id)
);

-- Blog posts
CREATE TABLE IF NOT EXISTS posts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL DEFAULT 'Untitled',
    slug           TEXT UNIQUE NOT NULL,
    excerpt        TEXT NOT NULL DEFAULT '',
    body           TEXT NOT NULL DEFAULT '',
    cover_filename TEXT,
    published      INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    published_at   TEXT
);

-- Editable single pages (about, etc.)
CREATE TABLE IF NOT EXISTS pages (
    slug           TEXT PRIMARY KEY,
    title          TEXT NOT NULL DEFAULT '',
    body           TEXT NOT NULL DEFAULT '',
    image_filename TEXT,
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Site-wide settings (key/value)
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_photos_sort     ON photos(sort_order, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_photos_featured ON photos(featured);
CREATE INDEX IF NOT EXISTS idx_subcats_cat     ON subcategories(category_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_cats_sort       ON categories(sort_order, name);
CREATE INDEX IF NOT EXISTS idx_menu            ON menu_items(parent_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_posts_pub       ON posts(published, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_phototags_tag   ON photo_tags(tag_id);
-- Indexes on the photos columns added by migration live in db._migrate(), so that
-- they are created only after those columns are guaranteed to exist.
