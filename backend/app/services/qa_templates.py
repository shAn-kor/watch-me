"""Fixed Q&A strings (03 section 7, I-16). Answer text comes only from `fact.behavior`
and from these constants; the model never writes visitor-facing words."""

from __future__ import annotations

HEADING_ANSWERED = "Here is what has been filmed:"
HEADING_NOT_OBSERVED = "Not observed yet."
HINT_NOT_OBSERVED = "Check the list of situations that have not been filmed, or ask the shelter."
HEADING_HEALTH = "Ask the shelter's vet."
HINT_HEALTH = "Health information comes from the shelter, not from these clips."

NOTICE_IN_PERSON_CODE = "ask_shelter_in_person_meeting"
NOTICE_IN_PERSON_TEXT = "Ask the shelter about an in-person meeting."

TEMPLATE_STRINGS: frozenset[str] = frozenset(
    {
        HEADING_ANSWERED,
        HEADING_NOT_OBSERVED,
        HINT_NOT_OBSERVED,
        HEADING_HEALTH,
        HINT_HEALTH,
        NOTICE_IN_PERSON_TEXT,
    }
)
