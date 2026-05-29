import io
import json
import os
import re
import random
import time
import logging

from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Each Google Workspace MIME type maps to a list of (export_mime, extension) to produce.
# Files are exported in every format listed — PDF always first, Office second where applicable.
EXPORT_FORMATS: dict[str, list[tuple[str, str]]] = {
    "application/vnd.google-apps.document": [
        ("application/pdf", ".pdf"),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    ],
    "application/vnd.google-apps.spreadsheet": [
        ("application/pdf", ".pdf"),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    ],
    "application/vnd.google-apps.presentation": [
        ("application/pdf", ".pdf"),
        ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    ],
    "application/vnd.google-apps.drawing": [
        ("application/pdf", ".pdf"),
    ],
}

_MIME_EXTENSIONS: dict[str, str] = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/webm": ".webm",
    "video/ogg": ".ogv",
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "text/plain": ".txt",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
}


def _ext_for_mime(mime: str) -> str | None:
    """Return the canonical extension for a MIME type, or None if unknown."""
    if mime in _MIME_EXTENSIONS:
        return _MIME_EXTENSIONS[mime]
    if mime.startswith("video/"):
        return "." + mime.split("/")[-1]
    if mime.startswith("audio/"):
        return "." + mime.split("/")[-1]
    return None


_MIME_LABELS: dict[str, str] = {
    "video/mp4": "video (mp4)",
    "video/quicktime": "video (mov)",
    "video/x-msvideo": "video (avi)",
    "video/webm": "video (webm)",
    "application/pdf": "pdf",
    "application/vnd.google-apps.document": "Google Doc",
    "application/vnd.google-apps.spreadsheet": "Google Sheet",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.drawing": "Google Drawing",
    "application/vnd.google-apps.video": "video (Google)",
    "image/jpeg": "immagine (jpeg)",
    "image/png": "immagine (png)",
    "audio/mpeg": "audio (mp3)",
}


def _mime_label(mime: str) -> str:
    if mime in _MIME_LABELS:
        return _MIME_LABELS[mime]
    if mime.startswith("video/"):
        return f"video ({mime.split('/')[-1]})"
    if mime.startswith("audio/"):
        return f"audio ({mime.split('/')[-1]})"
    if mime.startswith("image/"):
        return f"immagine ({mime.split('/')[-1]})"
    return mime


_RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 5


def sanitize(name: str, max_len: int = 180) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name[:max_len].strip(". ")


def _error_reason(exc: HttpError) -> str:
    try:
        content = json.loads(exc.content)
        return content.get("error", {}).get("errors", [{}])[0].get("reason", "")
    except Exception:
        return ""


def _is_retryable(exc: HttpError) -> bool:
    if exc.resp.status in _RETRYABLE_STATUSES:
        return True
    if exc.resp.status == 403 and _error_reason(exc) in _RATE_LIMIT_REASONS:
        return True
    return False


def _with_retry(fn):
    """Call fn(), retrying on rate-limit / transient errors with exponential backoff."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return fn()
        except HttpError as exc:
            if _is_retryable(exc) and attempt < MAX_RETRIES:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "Rate limit / server error (attempt %d/%d), retrying in %.1fs...",
                    attempt + 1, MAX_RETRIES, wait,
                )
                time.sleep(wait)
            else:
                raise


def download_file(
    drive_svc,
    file_id: str,
    dest_dir: str,
    hint_title: str | None = None,
    failures: list | None = None,
) -> list[str]:
    """
    Download a Drive file to dest_dir.
    Google Workspace files are exported in all configured formats (PDF + Office).
    Returns a list of successfully written paths (empty on total failure).
    Failed downloads are appended to `failures` as {"title": ..., "file_id": ..., "reason": ...}.
    """
    try:
        meta = _with_retry(lambda: drive_svc.files().get(
            fileId=file_id,
            fields="id,name,mimeType,modifiedTime",
        ).execute())
    except HttpError as exc:
        logger.error("Metadata fetch failed for %s: %s", file_id, exc)
        if failures is not None:
            failures.append({"title": hint_title or file_id, "file_id": file_id, "reason": str(exc)})
        return []

    mime = meta.get("mimeType", "")
    name = sanitize(hint_title or meta.get("name", file_id))

    allowed_env = os.getenv("ALLOWED_MIME_TYPES", "").strip()
    if allowed_env and not mime.startswith("application/vnd.google-apps."):
        allowed = {m.strip() for m in allowed_env.split(",") if m.strip()}
        if mime not in allowed:
            logger.debug("Skipping %s (%s) — not in ALLOWED_MIME_TYPES", name, mime)
            return []

    os.makedirs(dest_dir, exist_ok=True)

    if mime in EXPORT_FORMATS:
        paths = []
        for export_mime, ext in EXPORT_FORMATS[mime]:
            path = _export(drive_svc, file_id, meta["name"], name, dest_dir, export_mime, ext, mime, failures)
            if path:
                paths.append(path)
        return paths

    if mime.startswith("application/vnd.google-apps."):
        logger.info("Skipping non-exportable Google file: %s (%s)", meta["name"], mime)
        return []

    path = _download_binary(drive_svc, file_id, meta["name"], name, dest_dir, mime, failures)
    return [path] if path else []


def _export(drive_svc, file_id: str, display_name: str, safe_name: str, dest_dir: str, mime: str, ext: str, source_mime: str, failures: list | None = None) -> str | None:
    dest_path = os.path.join(dest_dir, safe_name + ext)
    logger.info("Exporting  %s → %s", display_name, dest_path)
    try:
        _with_retry(lambda: _write_stream(drive_svc.files().export_media(fileId=file_id, mimeType=mime), dest_path))
        return dest_path
    except HttpError as exc:
        logger.error("Export failed for %s: %s", display_name, exc)
        if failures is not None:
            failures.append({"title": display_name, "file_id": file_id, "reason": str(exc), "mime": _mime_label(source_mime)})
        return None


def _download_binary(drive_svc, file_id: str, display_name: str, safe_name: str, dest_dir: str, source_mime: str, failures: list | None = None) -> str | None:
    correct_ext = _ext_for_mime(source_mime)
    if correct_ext:
        base, existing_ext = os.path.splitext(safe_name)
        if existing_ext.lower() != correct_ext.lower():
            logger.info("Renaming %s%s → %s%s (MIME: %s)", base, existing_ext, base, correct_ext, source_mime)
        dest_path = os.path.join(dest_dir, base + correct_ext)
    else:
        dest_path = os.path.join(dest_dir, safe_name)
    logger.info("Downloading %s → %s", display_name, dest_path)
    try:
        _with_retry(lambda: _write_stream(drive_svc.files().get_media(fileId=file_id), dest_path))
        return dest_path
    except HttpError as exc:
        reason = _error_reason(exc)
        if exc.resp.status == 403:
            if reason == "cannotDownloadFile":
                logger.warning("Download restricted for %s — skipping", display_name)
            else:
                logger.warning("Access denied for %s — skipping", display_name)
        else:
            logger.error("Download failed for %s: %s", display_name, exc)
        if failures is not None:
            failures.append({"title": display_name, "file_id": file_id, "reason": reason or str(exc), "mime": _mime_label(source_mime)})
        return None


def _write_stream(request, dest_path: str):
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request, chunksize=8 * 1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    with open(dest_path, "wb") as fh:
        fh.write(buf.getvalue())
