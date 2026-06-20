"""Helpers: markdown + HTML rendering, slugs, excerpts, date formatting."""
import html as _html
import re
from datetime import datetime

import bleach
import markdown as md
from markupsafe import Markup
from slugify import slugify as _slugify

_ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "img", "figure",
    "figcaption", "hr", "br", "span", "div", "table", "thead", "tbody",
    "tr", "th", "td", "del", "ins", "sup", "sub", "u", "s",
}
_ALLOWED_ATTRS = {
    "*": ["class", "id"],
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "td": ["align"],
    "th": ["align"],
}


def render_markdown(text: str) -> Markup:
    """Render trusted-author markdown to sanitized HTML."""
    if not text:
        return Markup("")
    html = md.markdown(text, extensions=["extra", "sane_lists", "smarty", "nl2br"])
    clean = bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)
    clean = bleach.linkify(clean)
    return Markup(clean)


def clean_html(html: str) -> Markup:
    """Sanitize author-supplied HTML (from the WYSIWYG blog editor) for display."""
    if not html:
        return Markup("")
    return Markup(
        bleach.clean(str(html), tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)
    )


def make_slug(text: str) -> str:
    return _slugify(text) or "untitled"


def unique_slug(db, text, table="posts", exclude_id=None):
    base = make_slug(text)
    slug, i = base, 2
    while True:
        if exclude_id is None:
            hit = db.execute(
                f"SELECT 1 FROM {table} WHERE slug = ?", (slug,)
            ).fetchone()
        else:
            hit = db.execute(
                f"SELECT 1 FROM {table} WHERE slug = ? AND id != ?", (slug, exclude_id)
            ).fetchone()
        if not hit:
            return slug
        slug = f"{base}-{i}"
        i += 1


def unique_category_slug(db, name, exclude_id=None):
    """A category slug unique across all categories."""
    base = make_slug(name)
    slug, i = base, 2
    while True:
        if exclude_id is None:
            hit = db.execute(
                "SELECT 1 FROM categories WHERE slug = ?", (slug,)
            ).fetchone()
        else:
            hit = db.execute(
                "SELECT 1 FROM categories WHERE slug = ? AND id != ?", (slug, exclude_id)
            ).fetchone()
        if not hit:
            return slug
        slug = f"{base}-{i}"
        i += 1


def unique_subcategory_slug(db, category_id, name, exclude_id=None):
    """A subcategory slug unique within its parent category."""
    base = make_slug(name)
    slug, i = base, 2
    while True:
        if exclude_id is None:
            hit = db.execute(
                "SELECT 1 FROM subcategories WHERE category_id = ? AND slug = ?",
                (category_id, slug),
            ).fetchone()
        else:
            hit = db.execute(
                "SELECT 1 FROM subcategories WHERE category_id = ? AND slug = ? AND id != ?",
                (category_id, slug, exclude_id),
            ).fetchone()
        if not hit:
            return slug
        slug = f"{base}-{i}"
        i += 1


def excerpt_from(text: str, length: int = 180) -> str:
    plain = re.sub(r"<[^>]+>", " ", text or "")              # strip HTML tags
    plain = _html.unescape(plain)
    plain = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", plain)  # md links/images -> text
    plain = re.sub(r"[#>*_`~|-]", " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) <= length:
        return plain
    return plain[:length].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def format_date(value, fmt="%B %d, %Y"):
    if not value:
        return ""
    if isinstance(value, str):
        for parse in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                value = datetime.strptime(value, parse)
                break
            except ValueError:
                continue
        else:
            return value
    day = str(value.day)  # no leading zero, portable
    return value.strftime(fmt).replace(value.strftime("%d"), day, 1)
