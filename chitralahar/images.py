"""Image ingestion: validate, fix orientation, build display + thumbnail JPEGs."""
import io
import os
import uuid
import warnings
from pathlib import Path

from flask import current_app
from PIL import Image, ImageDraw, ImageFont, ImageOps

# Guard against decompression-bomb images (a tiny file that decodes to a huge
# bitmap → memory exhaustion). Turn the warning into an error so our upload
# try/except converts it into a clean "unreadable image" rejection.
Image.MAX_IMAGE_PIXELS = int(os.environ.get("CHITRALAHAR_MAX_IMAGE_PIXELS", 64_000_000))
warnings.simplefilter("error", Image.DecompressionBombWarning)

try:  # optional iPhone HEIC/HEIF support
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:  # pragma: no cover - optional dependency
    HEIF_OK = False


def extract_exif(img: Image.Image) -> dict:
    """Pull the photographer-relevant EXIF fields into a small dict ('' if none)."""
    out = {}
    try:
        exif = img.getexif()
        ifd = exif.get_ifd(0x8769)  # Exif sub-IFD: exposure data lives here
        model = str(exif.get(272) or "").strip()          # camera model
        make = str(exif.get(271) or "").strip()
        if model:
            out["camera"] = model if model.startswith(make.split(" ")[0] or "\0") else f"{make} {model}".strip()
        lens = str(ifd.get(0xA434) or "").strip()
        if lens:
            out["lens"] = lens
        f = ifd.get(33437)  # FNumber
        if f:
            out["aperture"] = "f/%g" % float(f)
        t = ifd.get(33434)  # ExposureTime
        if t:
            t = float(t)
            out["shutter"] = "1/%d s" % round(1 / t) if 0 < t < 1 else "%g s" % t
        iso = ifd.get(34855)
        if iso:
            out["iso"] = "ISO %d" % (iso[0] if isinstance(iso, (tuple, list)) else int(iso))
        fl = ifd.get(37386)  # FocalLength
        if fl:
            out["focal"] = "%g mm" % float(fl)
        dt = str(ifd.get(36867) or "").strip()  # DateTimeOriginal
        if dt:
            out["taken"] = dt.replace(":", "-", 2)
    except Exception:  # noqa: BLE001 — EXIF is best-effort, never block an upload
        pass
    return out


def allowed_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def _upload_root() -> Path:
    return Path(current_app.config["UPLOAD_FOLDER"])


def _resize_long_edge(img: Image.Image, max_edge: int) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_edge:
        return img.copy()
    if w >= h:
        new_w, new_h = max_edge, max(1, round(h * max_edge / w))
    else:
        new_h, new_w = max_edge, max(1, round(w * max_edge / h))
    return img.resize((new_w, new_h), Image.LANCZOS)


def _flatten(img: Image.Image) -> Image.Image:
    """Composite onto white and convert to RGB (theme is light)."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def _open_normalized(file_storage) -> Image.Image:
    try:
        img = Image.open(file_storage.stream)
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not read image: {exc}") from exc
    img = ImageOps.exif_transpose(img)  # honor camera rotation
    return _flatten(img)


def _save_jpeg(img: Image.Image, path: Path):
    img.save(
        path, "JPEG",
        quality=current_app.config["JPEG_QUALITY"],
        optimize=True, progressive=True,
    )


def process_upload(file_storage) -> dict:
    """Keep the full-resolution original, plus a display (~DISPLAY_SIZE) and a
    thumbnail. Returns the stored names. Raises ValueError on unreadable input."""
    raw = file_storage.read()
    if not raw:
        raise ValueError("Empty upload")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not read image: {exc}") from exc
    exif = extract_exif(img)
    img = ImageOps.exif_transpose(img)
    flat = _flatten(img)

    stem = uuid.uuid4().hex
    name = f"{stem}.jpg"
    display = _resize_long_edge(flat, current_app.config["DISPLAY_SIZE"])
    _save_jpeg(display, _upload_root() / "photos" / name)
    thumb = _resize_long_edge(flat, current_app.config["THUMB_SIZE"])
    _save_jpeg(thumb, _upload_root() / "thumbs" / name)

    # Keep the untouched original bytes for full-resolution private downloads.
    src_name = file_storage.filename or ""
    ext = src_name.rsplit(".", 1)[-1].lower() if "." in src_name else "jpg"
    if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
        ext = "jpg"
    orig_filename = f"{stem}.{ext}"
    try:
        (_upload_root() / "originals" / orig_filename).write_bytes(raw)
    except OSError:
        orig_filename = ""  # degrade gracefully if originals/ isn't writable

    import json
    return {
        "filename": name,
        "thumb_filename": name,
        "width": display.size[0],
        "height": display.size[1],
        "orig_name": src_name or "image",
        "orig_filename": orig_filename,
        "exif": json.dumps(exif) if exif else "",
    }


def process_misc_image(file_storage, max_edge=2200) -> str:
    """Save a cover/portrait image into misc/. Returns the filename."""
    img = _open_normalized(file_storage)
    img = _resize_long_edge(img, max_edge)
    name = f"{uuid.uuid4().hex}.jpg"
    _save_jpeg(img, _upload_root() / "misc" / name)
    return name


def process_png(file_storage, max_edge=600) -> str:
    """Save a logo/favicon as a PNG into misc/, preserving transparency.

    Logos sit on light *and* dark templates, so we keep the alpha channel rather
    than flattening onto white. Returns the stored filename.
    """
    try:
        img = Image.open(file_storage.stream)
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not read image: {exc}") from exc
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGBA", "RGB", "LA", "L"):
        img = img.convert("RGBA")
    img = _resize_long_edge(img, max_edge)
    name = f"{uuid.uuid4().hex}.png"
    img.save(_upload_root() / "misc" / name, "PNG", optimize=True)
    return name


def delete_photo_files(photo):
    root = _upload_root()
    keys = photo.keys()
    for sub, key in (("photos", "filename"), ("thumbs", "thumb_filename")):
        name = photo[key]
        if name:
            try:
                (root / sub / name).unlink(missing_ok=True)
            except OSError:
                pass
    # the kept original (if any)
    orig = photo["orig_filename"] if "orig_filename" in keys else ""
    if orig:
        try:
            (root / "originals" / orig).unlink(missing_ok=True)
        except OSError:
            pass
    # drop any cached watermarked variants for this photo
    for prefix, key in (("full_", "filename"), ("thumb_", "thumb_filename")):
        name = photo[key]
        if name:
            try:
                (root / "wm" / (prefix + name)).unlink(missing_ok=True)
            except OSError:
                pass


def delete_misc_file(name):
    if not name:
        return
    try:
        (_upload_root() / "misc" / name).unlink(missing_ok=True)
    except OSError:
        pass


# --------------------------- Watermarking ---------------------------
# Watermarks are applied dynamically to PUBLIC images only and cached under
# uploads/wm/. The stored originals stay clean, so private-album downloads are
# never watermarked.

def _wm_dir():
    d = _upload_root() / "wm"
    d.mkdir(parents=True, exist_ok=True)
    return d


def clear_watermark_cache():
    """Drop all cached watermarked images (call when watermark settings change)."""
    d = _upload_root() / "wm"
    if d.exists():
        for f in d.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass


def fonts_dir() -> Path:
    # package static/fonts/ — fixed location, so no app context needed
    return Path(__file__).resolve().parent / "static" / "fonts"


def available_fonts():
    """[(display_name, filename), …] for fonts the operator dropped in static/fonts/."""
    d = fonts_dir()
    out = []
    if d.is_dir():
        for f in sorted(d.iterdir(), key=lambda p: p.name.lower()):
            if f.suffix.lower() in (".ttf", ".otf", ".ttc"):
                out.append((f.stem, f.name))
    return out


def _load_font(font_name, size):
    """Load a watermark font from static/fonts/ by filename, else the built-in default.
    The filename is validated to live directly in fonts/ (no path traversal)."""
    if font_name:
        p = (fonts_dir() / font_name)
        try:
            if p.parent == fonts_dir() and p.exists():
                return ImageFont.truetype(str(p), size)
        except Exception:  # noqa: BLE001
            pass
    return ImageFont.load_default(size=size)


_CORNER_ANCHOR = {"br": "rd", "bl": "ld", "tr": "ra", "tl": "la", "center": "mm"}


def _hex_rgb(value, default=(255, 255, 255)):
    v = (value or "").strip().lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    try:
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except (ValueError, IndexError):
        return default


def _luminance(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _corner_xy(position, W, H, m):
    return {
        "br": (W - m, H - m), "bl": (m, H - m), "tr": (W - m, m),
        "tl": (m, m), "center": (W // 2, H // 2),
    }.get(position, (W - m, H - m))


def _tile_across(overlay, tile, W, H):
    sx, sy = max(1, int(tile.width * 1.18)), max(1, int(tile.height * 1.18))
    for y in range(-tile.height, H + tile.height, sy):
        for x in range(-tile.width, W + tile.width, sx):
            overlay.alpha_composite(tile, (x, y))


def _watermark_mark(settings, base_w, alpha):
    """The watermark image (logo), scaled to watermark_scale% of base width, with
    opacity applied to its alpha channel. None if not configured/loadable."""
    name = settings.get("watermark_image")
    if not name:
        return None
    path = _upload_root() / "misc" / name
    if not path.exists():
        return None
    try:
        mark = Image.open(path).convert("RGBA")
    except Exception:  # noqa: BLE001
        return None
    try:
        scale = int(settings.get("watermark_scale") or 18)
    except (TypeError, ValueError):
        scale = 18
    scale = max(3, min(100, scale))
    target_w = max(1, int(base_w * scale / 100))
    if mark.width != target_w:
        ratio = target_w / mark.width
        mark = mark.resize((target_w, max(1, int(mark.height * ratio))), Image.LANCZOS)
    a = mark.getchannel("A").point(lambda v: int(v * alpha / 255))
    mark.putalpha(a)
    return mark


def _apply_watermark(img, settings):
    """Composite the configured watermark (text or image) onto an RGBA image."""
    W, H = img.size
    position = settings.get("watermark_position") or "br"
    try:
        opacity = int(settings.get("watermark_opacity") or 35)
    except (TypeError, ValueError):
        opacity = 35
    alpha = max(8, min(245, round(255 * opacity / 100)))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    m = int(W * 0.025)

    if (settings.get("watermark_type") or "text") == "image":
        mark = _watermark_mark(settings, W, alpha)
        if mark is None:
            return img
        if position == "tiled":
            _tile_across(overlay, mark.rotate(30, expand=True, resample=Image.BICUBIC), W, H)
        else:
            x, y = _corner_xy(position, W, H, m)
            ax = x - mark.width if position in ("br", "tr") else (x - mark.width // 2 if position == "center" else x)
            ay = y - mark.height if position in ("br", "bl") else (y - mark.height // 2 if position == "center" else y)
            overlay.alpha_composite(mark, (max(0, ax), max(0, ay)))
    else:
        text = (settings.get("watermark_text") or settings.get("site_title") or "©").strip() or "©"
        try:
            fs = int(settings.get("watermark_font_size") or 100)
        except (TypeError, ValueError):
            fs = 100
        # font size is calibrated to the display width and scaled per image so the
        # watermark looks the same relative size on the full image and the thumbnail.
        ref = current_app.config.get("DISPLAY_SIZE", 2200) or 2200
        size = max(10, int(fs * W / ref))
        font = _load_font(settings.get("watermark_font"), size)
        rgb = _hex_rgb(settings.get("watermark_color") or "#ffffff")
        fill = rgb + (alpha,)
        # contrasting shadow keeps the text legible on any photo
        shadow = (0, 0, 0, alpha) if _luminance(rgb) > 140 else (255, 255, 255, alpha)
        if position == "tiled":
            tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
            bbox = tmp.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            pad = max(8, th)
            tile = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
            ImageDraw.Draw(tile).text((pad, pad), text, font=font, fill=fill, anchor="la")
            _tile_across(overlay, tile.rotate(30, expand=True, resample=Image.BICUBIC), W, H)
        else:
            draw = ImageDraw.Draw(overlay)
            x, y = _corner_xy(position, W, H, m)
            anchor = _CORNER_ANCHOR.get(position, "rd")
            off = max(1, size // 40)
            draw.text((x + off, y + off), text, font=font, fill=shadow, anchor=anchor)
            draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

    return Image.alpha_composite(img, overlay)


def watermarked_file(src_path, cache_name, settings):
    """Path to a cached watermarked JPEG for src_path; generate it if missing.
    Falls back to the clean source if the image can't be processed. The cache is
    cleared whenever watermark settings change (see admin.settings)."""
    cache = _wm_dir() / cache_name
    if cache.exists():
        return cache
    try:
        img = ImageOps.exif_transpose(Image.open(src_path)).convert("RGBA")
        out = _apply_watermark(img, settings).convert("RGB")
        # temp file + atomic rename so concurrent workers can't serve a half file
        tmp = cache.with_name(cache.name + ".%d.tmp" % os.getpid())
        out.save(tmp, "JPEG", quality=current_app.config["JPEG_QUALITY"],
                 optimize=True, progressive=True)
        os.replace(tmp, cache)
    except Exception:  # noqa: BLE001 — never break image serving over a bad file
        return src_path
    return cache
