"""File uploads: opt in with `extensions=[stk.files, ...]`.

Bytes live in `stk.files.store`, one row per upload in `stk_file`, and the routes
in `stk.files.views`. See docs/src/content/docs/api.md#file-uploads.
"""

from pathlib import Path


def init_app(app):
    from stk.files.views import SNIFFED, bp, can_read

    app.config.setdefault("STK_UPLOAD_DIR", str(Path(app.instance_path) / "files"))
    app.config.setdefault("STK_UPLOAD_MAX_BYTES", 10 * 1024 * 1024)
    app.config.setdefault(
        "STK_UPLOAD_TYPES",
        ("image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"),
    )
    if unknown := set(app.config["STK_UPLOAD_TYPES"]) - SNIFFED:
        raise ValueError(f"STK_UPLOAD_TYPES has types stk cannot sniff: {unknown}")
    # Replace after building the app: `app.file_access = async def (user, file)`.
    app.file_access = can_read
    app.register_blueprint(bp)
