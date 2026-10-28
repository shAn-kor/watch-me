# ADR-0029: Day-1 timestamp spike with an 80% bar before building on timestamps

- Status: Accepted
- Date: 2026-10-28

## Context

- Muse Spark does not document timestamp grounding (DESIGN 3.1, ADR-0020). If cited ranges are wrong, the evidence link is meaningless.
- Red-team review added a numeric timestamp bar with a segment fallback (PRD header).
- The deadline is 2026-11-05 11:00 KST.

## Decision

- Day 1: run AI-1 and AI-2 on 10 hand-labeled clips (`eval/spike_labels.jsonl`) with `tools/spike_timestamps.py`. It reports the share of cited ranges that contain the labeled behavior, time per session, and token cost.
- Bar: at least 80% of cited ranges contain the behavior. Below the bar: switch to fixed 10 s segments, and the model cites segment IDs.
- The same spike supplies the first measures for NFR-1 (under 5 minutes) and NFR-2 (cost).
- Build order step 1: `ai/` protocols, `mock` and one real adapter, frame sampling, spike script.

## Alternatives considered

- Build first, measure later: rejected, the whole data model depends on ranges.
- A higher or lower bar: 80% is the PRD choice; no evidence for the number is given (unverified).

## Consequences

- Positive: an early, cheap go/no-go; the fallback has a trigger.
- Negative: 10 clips is a small sample; the hand-check is subjective.
- Follow-up: record the result and mode in config.

## Open issues

- The spike needs a working provider on day 1, but the dev provider is undecided and the Meta credit has not arrived (DESIGN sections 4 and 13). The inputs do not say which clips the spike uses.

## Related

PRD AI-2, NFR-1, NFR-2, section 7; ADR-0019, ADR-0020, ADR-0021.
