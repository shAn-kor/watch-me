"""ORM models. Importing this package registers every table on `Base.metadata`
(Alembic `env.py` relies on that)."""

from app.models.clip import Clip
from app.models.cost_ledger import CostLedger
from app.models.dog import Dog
from app.models.fact import Fact, FactEvidence
from app.models.filming_session import FilmingSession
from app.models.job import Job
from app.models.member import Member
from app.models.org import Org
from app.models.playback import PlaybackEvent
from app.models.qa_log import QaLog
from app.models.transcript import Segment, TranscriptSegment

__all__ = [
    "Clip",
    "CostLedger",
    "Dog",
    "Fact",
    "FactEvidence",
    "FilmingSession",
    "Job",
    "Member",
    "Org",
    "PlaybackEvent",
    "QaLog",
    "Segment",
    "TranscriptSegment",
]
