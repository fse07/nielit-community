"""File upload helpers."""
import os
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import current_app
from PIL import Image


def _ext(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def save_image(file_storage, subdir="images", max_dim=1600):
    """Save an uploaded image, optionally resizing; return filename only."""
    ext = _ext(file_storage.filename)
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise ValueError("Unsupported image extension")
    name = f"{uuid.uuid4().hex}.{ext}"
    base = Path(current_app.config["UPLOAD_FOLDER"]) / subdir
    base.mkdir(parents=True, exist_ok=True)
    path = base / name
    file_storage.save(path)

    # Resize if huge
    try:
        with Image.open(path) as im:
            im = im.convert("RGB") if ext in {"jpg", "jpeg"} else im
            if max(im.size) > max_dim:
                im.thumbnail((max_dim, max_dim))
                im.save(path, optimize=True, quality=85)
    except Exception:
        pass  # Non-image or unsupported
    return name


def save_video(file_storage):
    """Save an uploaded video; return filename."""
    ext = _ext(file_storage.filename)
    if ext not in current_app.config["ALLOWED_VIDEO_EXTENSIONS"]:
        raise ValueError("Unsupported video extension")
    name = f"{uuid.uuid4().hex}.{ext}"
    base = Path(current_app.config["UPLOAD_FOLDER"]) / "videos"
    base.mkdir(parents=True, exist_ok=True)
    file_storage.save(base / name)
    return name


def save_avatar(file_storage):
    """Save an avatar image; return filename."""
    ext = _ext(file_storage.filename)
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise ValueError("Unsupported image extension")
    name = f"{uuid.uuid4().hex}.{ext}"
    base = Path(current_app.config["UPLOAD_FOLDER"]) / "avatars"
    base.mkdir(parents=True, exist_ok=True)
    path = base / name
    file_storage.save(path)
    try:
        with Image.open(path) as im:
            im = im.convert("RGB") if ext in {"jpg", "jpeg"} else im
            im.thumbnail((400, 400))
            im.save(path, optimize=True, quality=85)
    except Exception:
        pass
    return name
