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
    os.makedirs(dest_dir, exist_ok=True)

    if mime in EXPORT_FORMATS:
        paths = []
        for export_mime, ext in EXPORT_FORMATS[mime]:
            path = _export(drive_svc, file_id, meta["name"], name, dest_dir, export_mime, ext, failures)
            if path:
                paths.append(path)
        return paths

    if mime.startswith("application/vnd.google-apps."):
        logger.info("Skipping non-exportable Google file: %s (%s)", meta["name"], mime)
        return []

    path = _download_binary(drive_svc, file_id, meta["name"], name, dest_dir, failures)
    return [path] if path else []


def _export(drive_svc, file_id: str, display_name: str, safe_name: str, dest_dir: str, mime: str, ext: str, failures: list | None = None) -> str | None:
    dest_path = os.path.join(dest_dir, safe_name + ext)
    logger.info("Exporting  %s → %s", display_name, dest_path)
    try:
        _with_retry(lambda: _write_stream(drive_svc.files().export_media(fileId=file_id, mimeType=mime), dest_path))
        return dest_path
    except HttpError as exc:
        logger.error("Export failed for %s: %s", display_name, exc)
        if failures is not None:
            failures.append({"title": display_name, "file_id": file_id, "reason": str(exc)})
        return None


def _download_binary(drive_svc, file_id: str, display_name: str, safe_name: str, dest_dir: str, failures: list | None = None) -> str | None:
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
            failures.append({"title": display_name, "file_id": file_id, "reason": reason or str(exc)})
        return None


def _write_stream(request, dest_path: str):
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request, chunksize=8 * 1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    with open(dest_path, "wb") as fh:
        fh.write(buf.getvalue())
