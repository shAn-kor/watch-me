"""Router registry. `main.create_app` includes every router in `ROUTERS`, in order.

One line per lane; a lane appends its own router(s) in its slot. Until a lane
lands, its slot is a comment.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import auth, clips, dogs, facts, health, me, public, sessions

ROUTERS: list[APIRouter] = []

ROUTERS.extend([auth.router, me.router, health.router])  # [slot S1]
ROUTERS.extend([dogs.router])  # [slot S2]
ROUTERS.extend([sessions.router, clips.router])  # [slot S3]
ROUTERS.extend([facts.router])  # [slot S4]
# [slot S5] public (profile), media -> public.router, media.router
ROUTERS.extend([public.router])  # [slot S6] ask route; S5 adds the profile route to the same router
# [slot I]  admin                 -> admin.router (phase 3)
