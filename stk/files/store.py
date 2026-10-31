"""Content-addressed bytes on local disk: `<STK_UPLOAD_DIR>/<sha[:2]>/<sha>`.

Equal bytes are stored once. Keys are sha256 hex digests, never user input.

# ponytail: local disk on one machine. Move the same keys to S3/R2 when a second
# app server needs the files or the uploads outgrow the disk.
"""

import hashlib
import os
import re
import tempfile
from pathlib import Path

from quart import current_app

SHA256 = re.compile(r"[0-9a-f]{64}")


def path(sha256: str) -> Path:
    # The one place a key becomes a path: 64 hex characters cannot climb out.
    if not SHA256.fullmatch(sha256):
        raise ValueError(f"not a sha256 hex digest: {sha256!r}")
    return Path(current_app.config["STK_UPLOAD_DIR"]) / sha256[:2] / sha256


def save(data: bytes) -> str:
    """Store bytes and return their sha256. A crash never leaves a partial file:
    the temp file sits beside its destination, so the rename is atomic."""
    sha256 = hashlib.sha256(data).hexdigest()
    dest = path(sha256)
    if dest.is_file():
        return sha256
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return sha256


def open(sha256: str):
    return path(sha256).open("rb")


def exists(sha256: str) -> bool:
    return path(sha256).is_file()


def delete(sha256: str) -> None:
    """Remove the bytes. Rows share bytes, so check no `File` still names them."""
    path(sha256).unlink()
