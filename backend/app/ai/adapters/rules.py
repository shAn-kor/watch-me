"""`rules`: the WordingChecker with no network (04 section 8.5).

The banned-word layer runs inline in the services (`domain.wording`), not
here. This adapter is the configured state "no model pass": it returns `none`
for every item, makes no call, and yields no `Usage`. No `check_unavailable`
flag follows from it, because the absence of the model pass is configuration,
not a failure.
"""

from __future__ import annotations

from app.ai.types import CheckRequest, CheckResult, Usage


class RulesChecker:
    def check(self, req: CheckRequest) -> tuple[list[CheckResult], list[Usage]]:
        return [CheckResult(ref=i.ref, kind="none", phrase=None) for i in req.items], []
