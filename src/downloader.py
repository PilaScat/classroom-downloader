import io
import os
import re
import logging
import time

from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Google Workspace MIME types that can be exported as PDF
EXPORTABLE_AS_PDF = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
    "application/vnd.google-apps.drawing",
}

# Google Workspace types that cannot be meaningfully exported
UNEXPORTABLE = {
    "application/vnd.google-apps.form",
    "application/vnd.google-apps.site",
    "application/vnd.google-apps.map",
    "application/vnd.google-apps.script",
}

PDF_MIME = "application/pdf"


def sanitize(name: str, max_len: int = 180) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name[:max_len].strip(". ")


def download_file(drive_svc, file_id: str, dest_dir: str, hint_title: str | None = None) -> str | None:
    """
    Download a Drive file to dest_dir.
    Google Docs/Sheets/Slides are exported as PDF.
    Returns the destination path, or None on failure.
    """
    try:
        meta = drive_svc.files().get(
            fileId=file_id,
            fields="id,name,mimeType,modifiedTime",
        ).execute()
    except HttpError as exc:
        logger.error("Metadata fetch failed for %s: %s", file_id, exc)
        return None

    mime = meta.get("mimeType", "")
    name = sanitize(hint_title or meta.get("name", file_id))
    os.makedirs(dest_dir, exist_ok=True)

    if mime in EXPORTABLE_AS_PDF:
        return _export_as_pdf(drive_svc, file_id, meta["name"], name, dest_dir)

    if mime.startswith("application/vnd.google-apps."):
        logger.info("Skipping non-exportable Google file: %s (%s)", meta["name"], mime)
        return None

    return _download_binary(drive_svc, file_id, meta["name"], name, dest_dir)


def _export_as_pdf(drive_svc, file_id: str, display_name: str, safe_name: str, dest_dir: str) -> str | None:
    dest_path = os.path.join(dest_dir, safe_name + ".pdf")
    logger.info("Exporting  %s → %s", display_name, dest_path)
    try:
        request = drive_svc.files().export_media(fileId=file_id, mimeType=PDF_MIME)
        _write_stream(request, dest_path)
        return dest_path
    except HttpError as exc:
        logger.error("Export failed for %s: %s", display_name, exc)
        return None


def _download_binary(drive_svc, file_id: str, display_name: str, safe_name: str, dest_dir: str) -> str | None:
    dest_path = os.path.join(dest_dir, safe_name)
    logger.info("Downloading %s → %s", display_name, dest_path)
    try:
        request = drive_svc.files().get_media(fileId=file_id)
        _write_stream(request, dest_path)
        return dest_path
    except HttpError as exc:
        if exc.resp.status == 403:
            logger.warning("Access denied for %s — skipping", display_name)
        else:
            logger.error("Download failed for %s: %s", display_name, exc)
        return None


def _write_stream(request, dest_path: str):
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request, chunksize=8 * 1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    with open(dest_path, "wb") as fh:
        fh.write(buf.getvalue())
