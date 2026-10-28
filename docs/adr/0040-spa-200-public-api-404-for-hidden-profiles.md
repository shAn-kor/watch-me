# ADR-0040: SPA shell returns 200; the public API returns 404 for hidden profiles

- Status: Accepted
- Date: 2026-10-28

## Context

- PRD v1.2 REV-5 said "unpublished returns HTTP 404; the page says 'not available'". The page is a React SPA route `/d/{slug}` (ADR-0015); a static host serves the same HTML shell for every route, so the page itself cannot be a 404 without server logic.
- Hidden means unpublished, adopted, deleted, or unknown slug. The API must not reveal which (ADR-0008, ADR-0038).

## Decision

- `GET /api/public/dogs/{slug}` returns `404 not_found` with the same body for every hidden case.
- The SPA HTML for `/d/{slug}` is served with 200; the app calls the API, gets 404, and renders the "not available" page.
- PRD v1.3 REV-5 acceptance: "the public API returns HTTP 404; the page says 'not available'".
- Profiles keep `X-Robots-Tag: noindex`.

## Alternatives considered

- Server-render a 404 status for the SPA route: rejected, needs a lookup in the static path for no R1 benefit.
- Return 200 with an empty body from the API: rejected, clients cannot tell hidden from valid.

## Consequences

- Positive: one uniform hidden response; no state leak; simple static serving.
- Negative: a link checker sees HTTP 200 for a hidden profile's page.

## Related

PRD REV-5, PUB-0; API spec public endpoints; ADR-0008, ADR-0015, ADR-0036.
