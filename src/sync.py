import json
import logging
import os
import re
from datetime import datetime, timezone

import classroom as cl
import downloader as dl

logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", "/data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", "/downloads")


def _safe(name: str, max_len: int = 100) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name[:max_len].strip(". ")


class Syncer:
    def __init__(self, classroom_svc, drive_svc):
        self.classroom = classroom_svc
        self.drive = drive_svc
        self._state = self._load_state()

    # ------------------------------------------------------------------ state

    def _load_state(self) -> dict:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as fh:
                return json.load(fh)
        return {"files": {}, "last_sync": None}

    def _save_state(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(STATE_FILE, "w") as fh:
            json.dump(self._state, fh, indent=2)

    def _already_downloaded(self, file_id: str) -> bool:
        entry = self._state["files"].get(file_id)
        if not entry:
            return False
        # Re-download if the local file was deleted
        return os.path.exists(entry["path"])

    def _record(self, file_id: str, path: str):
        self._state["files"][file_id] = {
            "path": path,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_state()

    # ------------------------------------------------------------------ sync

    def sync(self):
        total_new = 0
        for course in cl.list_courses(self.classroom):
            new = self._sync_course(course)
            total_new += new
        self._state["last_sync"] = datetime.now(timezone.utc).isoformat()
        self._save_state()
        logger.info("Sync done — %d new file(s) downloaded.", total_new)

    def _sync_course(self, course: dict) -> int:
        course_id = course["id"]
        course_name = course["name"]
        logger.info("Course: %s", course_name)
        course_dir = os.path.join(DOWNLOADS_DIR, _safe(course_name))
        count = 0

        # Materials posted by the teacher
        for item in cl.list_materials(self.classroom, course_id):
            title = item.get("title", item.get("id", "untitled"))
            dest = os.path.join(course_dir, "Materiali", _safe(title))
            count += self._download_materials(item.get("materials", []), dest)

        # Assignments / coursework
        for item in cl.list_coursework(self.classroom, course_id):
            title = item.get("title", item.get("id", "untitled"))
            dest = os.path.join(course_dir, "Compiti", _safe(title))
            count += self._download_materials(item.get("materials", []), dest)

        # Announcements
        for item in cl.list_announcements(self.classroom, course_id):
            title = item.get("text", "")[:60] or item.get("id", "annuncio")
            dest = os.path.join(course_dir, "Annunci")
            count += self._download_materials(item.get("materials", []), dest)

        return count

    def _download_materials(self, materials: list, dest_dir: str) -> int:
        count = 0
        for file_info in cl.extract_drive_files(materials):
            file_id = file_info["id"]
            title = file_info["title"]
            if self._already_downloaded(file_id):
                logger.debug("Already downloaded: %s", title)
                continue
            paths = dl.download_file(self.drive, file_id, dest_dir, title)
            if paths:
                self._record(file_id, paths[0])
                count += 1
        return count
