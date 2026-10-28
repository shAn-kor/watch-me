"""Media routes (01 section 7): clip video, captions, dog photo. `GET` and `HEAD`.

Cookie-only identity (no CSRF): a signed-in member of the dog's org may read their
own media; everyone else gets the public rule. Every denial is the same
`404 not_found`. Files go through Starlette `FileResponse` (ranges, ETag,
Last-Modified, 304). Rate limit: `limit("media")`, per IP.
"""

from __future__ import annotations

import hashlib
import os
import re
from email.utils import formatdate
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response

from app.api import deps
from app.db.uow import UnitOfWork
from app.errors import NotFound, Unauthenticated
from app.services.media_access_service import MediaFile
from app.services.views import Principal

router = APIRouter(tags=["media"])

_CLIP_NAME = re.compile(r"^([0-9a-f]{32})\.(mp4|vtt)$")
_HEADERS = {
    "Cache-Control": "private, no-cache",
    "Content-Disposition": "inline",
    "X-Robots-Tag": "noindex",
    "Vary": "Cookie",
}


def optional_principal(request: Request) -> Principal | None:
    """The signed-in member, or `None` for a missing, bad or revoked cookie."""
    try:
        return deps.current_principal(request)
    except Unauthenticated:
        return None


def _etag_matches(request: Request, etag: str) -> bool:
    if not etag:
        return False
    sent = [v.strip() for v in request.headers.get("if-none-match", "").split(",")]
    return etag in sent or "*" in sent


def _respond(request: Request, media: MediaFile) -> Response:
    if media.path is not None:
        try:
            stat = os.stat(media.path)
        except OSError as exc:
            raise NotFound() from exc
        file_response = FileResponse(
            media.path, media_type=media.content_type, headers=dict(_HEADERS), stat_result=stat
        )
        etag = file_response.headers.get("etag", "")
        if _etag_matches(request, etag):
            # Starlette's FileResponse does not answer If-None-Match itself.
            keep = {
                k: v
                for k, v in file_response.headers.items()
                if k.lower() in {h.lower() for h in _HEADERS} | {"etag", "last-modified"}
            }
            return Response(status_code=304, headers=keep)
        return file_response
    body = media.body or b""
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    headers = {**_HEADERS, "ETag": etag, "Accept-Ranges": "bytes"}
    if media.modified is not None:
        headers["Last-Modified"] = formatdate(media.modified.timestamp(), usegmt=True)
    if _etag_matches(request, etag):
        return Response(status_code=304, headers=headers)
    if request.method == "HEAD":
        headers["Content-Length"] = str(len(body))
        return Response(status_code=200, headers=headers, media_type=media.content_type)
    return Response(body, media_type=media.content_type, headers=headers)


@router.api_route(
    "/media/dogs/{dog_id}/photo.jpg",
    methods=["GET", "HEAD"],
    dependencies=[Depends(deps.limit("media"))],
)
def dog_photo(
    dog_id: str,
    request: Request,
    unit: UnitOfWork = Depends(deps.uow),
    who: Principal | None = Depends(optional_principal),
    container: Any = Depends(deps.get_container),
) -> Response:
    media = container.services.media_access_service.resolve_dog_photo(unit, dog_id, who)
    return _respond(request, media)


@router.api_route(
    "/media/{name}",
    methods=["GET", "HEAD"],
    dependencies=[Depends(deps.limit("media"))],
)
def clip_media(
    name: str,
    request: Request,
    unit: UnitOfWork = Depends(deps.uow),
    who: Principal | None = Depends(optional_principal),
    container: Any = Depends(deps.get_container),
) -> Response:
    match = _CLIP_NAME.match(name)
    if match is None:
        raise NotFound()
    clip_id, kind = match.groups()
    service = container.services.media_access_service
    if kind == "mp4":
        media = service.resolve_clip_video(unit, clip_id, who)
    else:
        media = service.resolve_clip_captions(unit, clip_id, who)
    return _respond(request, media)
