"""Router registry. `main.create_app` includes every router in `ROUTERS`, in order.

One line per lane; a lane appends its own router(s) in its slot. Until a lane
lands, its slot is a comment.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import auth, facts, health, me

ROUTERS: list[APIRouter] = []

ROUTERS.extend([auth.router, me.router, health.router])  # [slot S1]
# [slot S2] dogs                  -> dogs.router
# [slot S3] sessions, clips       -> sessions.router, clips.router
ROUTERS.extend([facts.router])  # [slot S4]
# [slot S5] public (profile), media -> public.router, media.router
# [slot S6] public (ask)          -> shares public.router with S5
# [slot I]  admin                 -> admin.router (phase 3)
