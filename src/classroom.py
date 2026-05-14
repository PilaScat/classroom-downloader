import logging
from typing import Iterator

logger = logging.getLogger(__name__)


def _paginate(request_fn, result_key: str):
    """Generic paginator for Google API list calls."""
    page_token = None
    while True:
        resp = request_fn(pageToken=page_token).execute()
        yield from resp.get(result_key, [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def list_courses(svc) -> Iterator[dict]:
    yield from _paginate(
        lambda pageToken: svc.courses().list(
            courseStates=["ACTIVE"], pageToken=pageToken, pageSize=50
        ),
        "courses",
    )


def list_materials(svc, course_id: str) -> Iterator[dict]:
    try:
        yield from _paginate(
            lambda pageToken: svc.courses().courseWorkMaterials().list(
                courseId=course_id, pageToken=pageToken, pageSize=50
            ),
            "courseWorkMaterial",
        )
    except Exception as exc:
        logger.warning("Cannot fetch materials for course %s: %s", course_id, exc)


def list_coursework(svc, course_id: str) -> Iterator[dict]:
    try:
        yield from _paginate(
            lambda pageToken: svc.courses().courseWork().list(
                courseId=course_id, pageToken=pageToken, pageSize=50
            ),
            "courseWork",
        )
    except Exception as exc:
        logger.warning("Cannot fetch coursework for course %s: %s", course_id, exc)


def list_announcements(svc, course_id: str) -> Iterator[dict]:
    try:
        yield from _paginate(
            lambda pageToken: svc.courses().announcements().list(
                courseId=course_id, pageToken=pageToken, pageSize=50
            ),
            "announcements",
        )
    except Exception as exc:
        logger.warning("Cannot fetch announcements for course %s: %s", course_id, exc)


def extract_drive_files(materials: list) -> list[dict]:
    """Return list of {id, title} for each Drive file in a materials list."""
    result = []
    for mat in materials:
        if "driveFile" in mat:
            df = mat["driveFile"]["driveFile"]
            result.append({"id": df["id"], "title": df.get("title", df["id"])})
    return result
