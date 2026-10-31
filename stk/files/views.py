import asyncio
import hashlib
import io
from pathlib import PurePosixPath

from PIL import Image, ImageOps
from quart import Blueprint, abort, current_app, g, request, send_file
from quart_security import auth_required, current_user
from sqlalchemy import select

from stk.files import store
from stk.files.models import File

bp = Blueprint("files", __name__)

# Leading bytes of each type stk recognizes; anything else is unknown and refused.
SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
)
IMAGE_FORMATS = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/gif": "GIF",
    "image/webp": "WEBP",
}
SNIFFED = {*IMAGE_FORMATS, "application/pdf"}
THUMB_SIDE = 480
# Decoding is width x height x 4 bytes of memory, whatever the file size.
MAX_PIXELS = 40_000_000
# Room for the multipart boundary and headers around the file itself.
MULTIPART_SLACK = 64 * 1024


def sniff(data: bytes) -> str | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return next((kind for magic, kind in SIGNATURES if data.startswith(magic)), None)


def thumbnail(data: bytes, content_type: str) -> bytes:
    """A WebP no wider or taller than THUMB_SIDE, re-encoded from pixels so no
    metadata survives. Raises OSError or ValueError for bytes that do not decode."""
    fmt = IMAGE_FORMATS[content_type]
    with Image.open(io.BytesIO(data), formats=[fmt]) as image:
        if image.width * image.height > MAX_PIXELS:
            raise ValueError("image has too many pixels")
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
        image.thumbnail((THUMB_SIDE, THUMB_SIDE))
        out = io.BytesIO()
        image.save(out, "WEBP", quality=80)
        return out.getvalue()


async def can_read(user, file: File) -> bool:
    """Default download check: the uploader or an admin."""
    return file.user_id == user.id or user.has_role("admin")


@bp.before_request
@auth_required("session")
async def before_request():
    pass


@bp.post("/files/")
async def upload():
    """Multipart upload of one `file` field. Send the CSRF token in the
    X-CSRFToken header: a token in the form makes the body parse before the
    size limit below applies."""
    limit = current_app.config["STK_UPLOAD_MAX_BYTES"]
    request.max_content_length = limit + MULTIPART_SLACK
    part = (await request.files).get("file")
    if part is None:
        return {"message": "No file in the 'file' field"}, 400
    name = PurePosixPath((part.filename or "").replace("\\", "/")).name
    name = "".join(c for c in name if c.isprintable())[:255]
    if not name:
        return {"message": "The file has no name"}, 400
    # ponytail: whole file in memory; stream to the store if the limit passes ~100 MB.
    data = part.read()
    if len(data) > limit:
        return {"message": f"Files are limited to {limit} bytes"}, 413
    content_type = sniff(data)
    if content_type not in current_app.config["STK_UPLOAD_TYPES"]:
        return {"message": "This file type is not allowed"}, 415

    sha256 = hashlib.sha256(data).hexdigest()
    found = await g.db_session.scalar(
        select(File).where(File.user_id == current_user.id, File.sha256 == sha256)
    )
    if found:
        return {"item": found.to_dict()}

    thumb_sha256 = None
    if content_type in IMAGE_FORMATS:
        try:
            thumb = await asyncio.to_thread(thumbnail, data, content_type)
        except (OSError, ValueError, Image.DecompressionBombError):
            return {"message": "The image could not be read"}, 400
        thumb_sha256 = await asyncio.to_thread(store.save, thumb)
    await asyncio.to_thread(store.save, data)
    file = File(
        sha256=sha256,
        size=len(data),
        content_type=content_type,
        filename=name,
        thumb_sha256=thumb_sha256,
        user_id=current_user.id,
    )
    g.db_session.add(file)
    await g.db_session.commit()
    return {"item": file.to_dict()}


async def readable(file_id: int) -> File:
    # 404 for a file the user may not read, so ids reveal nothing.
    file = await g.db_session.get(File, file_id)
    if file is None or not await current_app.file_access(current_user, file):
        abort(404)
    return file


async def serve(sha256, content_type, filename, attachment):
    response = await send_file(
        store.path(sha256),
        mimetype=content_type,
        as_attachment=attachment,
        attachment_filename=filename,
        add_etags=False,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@bp.get("/files/<int:file_id>")
async def download(file_id):
    file = await readable(file_id)
    attachment = file.content_type not in IMAGE_FORMATS
    return await serve(file.sha256, file.content_type, file.filename, attachment)


@bp.get("/files/<int:file_id>/thumb")
async def thumb(file_id):
    file = await readable(file_id)
    if file.thumb_sha256 is None:
        abort(404)
    return await serve(file.thumb_sha256, "image/webp", None, False)
