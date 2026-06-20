"""Configuration for the Chitralahar CMS."""
import os
from datetime import timedelta
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = PACKAGE_DIR.parent


def _abs(path_str: str) -> str:
    p = Path(path_str)
    return str(p if p.is_absolute() else BASE_DIR / p)


class Config:
    # --- Database ---
    DATABASE = _abs(os.environ.get("CHITRALAHAR_DATABASE", "instance/chitralahar.db"))

    # --- Uploads ---
    UPLOAD_FOLDER = str(PACKAGE_DIR / "static" / "uploads")
    # No upload-size limit by default. Set CHITRALAHAR_MAX_UPLOAD_MB to a positive
    # number to cap requests; 0 or unset means unlimited.
    _MAX_UPLOAD_MB = int(os.environ.get("CHITRALAHAR_MAX_UPLOAD_MB", "0"))
    MAX_CONTENT_LENGTH = (_MAX_UPLOAD_MB * 1024 * 1024) if _MAX_UPLOAD_MB > 0 else None
    ALLOWED_EXTENSIONS = {
        "jpg", "jpeg", "png", "webp", "gif", "tif", "tiff", "bmp", "heic", "heif",
    }

    # --- Image processing (long-edge pixels) ---
    THUMB_SIZE = 800      # gallery grid thumbnails
    DISPLAY_SIZE = 2200   # full-size view in the lightbox
    JPEG_QUALITY = 86

    # --- Sessions ---
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Send the session cookie only over HTTPS. Enable in production by setting
    # CHITRALAHAR_HTTPS=1 (see deploy/). Left off by default so plain-HTTP local
    # development still keeps you logged in.
    SESSION_COOKIE_SECURE = os.environ.get("CHITRALAHAR_HTTPS", "") == "1"
