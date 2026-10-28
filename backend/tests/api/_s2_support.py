"""Helpers of the lane S2 API tests (07 section 3.8)."""

from __future__ import annotations

import io
from typing import Any

import pytest

SLUG_RE = r"^[a-z2-9]{12}$"
LANE_S5 = "needs lane S5: public profile and /media routes"
LANE_S3_S4 = "needs lanes S3 and S4: sessions, clips and facts routes"


def csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def cross_lane(reason: str) -> Any:
    """xfail for the part of a 07 case that runs through another lane's routes."""
    return pytest.mark.xfail(reason=reason, strict=False)


def fresh(db: Any, model: Any, pk: str) -> Any:
    db.expire_all()
    return db.get(model, pk)


def make_jpeg_with_gps(size: tuple[int, int] = (3200, 2000)) -> bytes:
    """`photo_gps.jpg` of 07 section 2: a JPEG with EXIF make and GPS tags, built
    inline (no file in git)."""
    from PIL import Image

    img = Image.new("RGB", size, (200, 120, 60))
    exif = Image.Exif()
    exif[0x010F] = "TestCam"
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (37.0, 25.0, 19.0)
    gps[3] = "W"
    gps[4] = (122.0, 5.0, 1.0)
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def make_png(size: tuple[int, int] = (64, 48)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, (10, 200, 10)).save(buf, "PNG")
    return buf.getvalue()


def make_gif() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("P", (8, 8)).save(buf, "GIF")
    return buf.getvalue()


def dog_body(**over: Any) -> dict[str, Any]:
    body = {
        "name": "Biscuit",
        "sex": "male",
        "age_estimate": "about 3 years",
        "size": "medium",
        "location": "Portland, OR",
    }
    body.update(over)
    return body
