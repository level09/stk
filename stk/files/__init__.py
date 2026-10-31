"""File uploads: opt in with `extensions=[stk.files, ...]`.

Bytes live in `stk.files.store`, one row per upload in `stk_file`, and the routes
in `stk.files.views`. See docs/src/content/docs/api.md#file-uploads.
"""

from pathlib import Path


def init_app(app):
    from stk.files.views import MULTIPART_SLACK, SNIFFED, bp, can_read

    app.config.setdefault("STK_UPLOAD_DIR", str(Path(app.instance_path) / "files"))
    app.config.setdefault("STK_UPLOAD_MAX_BYTES", 10 * 1024 * 1024)
    # Quart caps every request body at MAX_CONTENT_LENGTH before a view runs, so
    # a larger upload limit would never take effect.
    limit, body_max = (
        app.config["STK_UPLOAD_MAX_BYTES"],
        app.config["MAX_CONTENT_LENGTH"],
    )
    if body_max is not None and limit + MULTIPART_SLACK > body_max:
        raise ValueError(
            f"STK_UPLOAD_MAX_BYTES ({limit}) plus {MULTIPART_SLACK} bytes of"
            f" multipart framing exceeds MAX_CONTENT_LENGTH ({body_max}): raise"
            " MAX_CONTENT_LENGTH or lower STK_UPLOAD_MAX_BYTES"
        )
    app.config.setdefault(
        "STK_UPLOAD_TYPES",
        ("image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"),
    )
    if unknown := set(app.config["STK_UPLOAD_TYPES"]) - SNIFFED:
        raise ValueError(f"STK_UPLOAD_TYPES has types stk cannot sniff: {unknown}")
    # Replace after building the app: `app.file_access = async def (user, file)`.
    app.file_access = can_read
    app.register_blueprint(bp)
