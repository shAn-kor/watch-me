# Watch Me visual system

The user requested a Meta-based visual refresh on 2026-11-04. This is a
Watch Me adaptation, not an official Meta component package or affiliation.

## Provenance

- Meta reference in the installed OmD catalog, `references/meta/DESIGN.md`.
- Official design principles: https://www.meta.com/design-at-meta/blog/designing-the-facebook-company-brand/
- Official product identity: https://www.meta.com/design-at-meta/blog/redefining-facebooks-brand-identity/

## Foundations

Use solid Meta Blue #0064e0 for primary actions, #0058c4 for hover/pressed,
Meta Ink #1c2b33 for text, #465a69 for secondary text, #ffffff for surfaces,
#f0f2f5 for the canvas, #f7f8fa for subtle surfaces, #e4e6eb for separators.
Input outlines retain #6b7178 for visible control boundaries. Keep existing
accessible success #1e6b3a and danger #b3261e. Warning colors retain #fff4d6,
#5c4300 and #8a6100. Never use the lighter Meta semantic colors as body text.
No gradients, colored shadows or decorative motion. All radii remain 8px.

## Typography and spacing

Use Avenir Next with Helvetica Neue, Helvetica and sans-serif fallbacks.
Avenir Next supplies the softer humanist letterforms requested in the correction. This follows the
Meta reference fallback while avoiding distribution of proprietary Optimistic
fonts. Body remains 16px/24px. Display 56px/60px at weight 400, page title 32px/40px,
section 24px/32px, subsection 20px/28px, metadata 14px/20px.
Use 4, 8, 12, 16, 24, 32, 48 and 64px spacing. Public page width 1200px; creator page width 1120px; creator reading
surface 800px; login form 400px. At 768px use 24px gutters and a two-column
public profile, with facts before coverage on mobile. At narrower widths use
16px page gutters and stack every column. No hidden or duplicated controls.

## Components and states

Primary actions have blue fill and white text. Secondary actions have neutral
fill and ink text. Hover and pressed states must not override disabled states.
Controls retain at least 44px targets and a visible 3px focus outline.
Input errors have a danger outline and existing text. Cards use a white
surface, a 1px separator border and 8px corners. Notice labels and text stay
visible. Fixed action bars retain safe-area padding.

## Content and behavior

Keep English interface copy. Preserve safety language verbatim and show the
notice before profile content. Keep all source facts, coverage totals, evidence,
unknown situations, contact links and question behavior. Review confirmation
still requires watching every cited range. Mock preview is explicitly separate
from the live Meta model demo and never proves backend or model correctness.

Profile reading order is safety notice, identity, shelter concerns, section
navigation, facts, questions, coverage, unknown situations and contact.
Shelter concerns remain before all facts on every viewport.

## Softer composition correction (2026-11-04)

The user found the first iteration too rigid compared with Meta pages.
Use a white public canvas, a large photo beside lightweight profile type,
unboxed fact groups, neutral navigation links and 48px section spacing.
The official Meta about page uses photography and large lightweight type as
its primary structure: https://www.meta.com/about/ . This adaptation keeps
text beside imagery for legibility, without image overlays or gradients.
Public fact and sidebar sections use whitespace and separators rather than
individual card outlines. Creator content keeps its existing layout while
using lighter heading weights and the same humanist font. Safety notice and
shelter concerns remain explicit and before facts. General notice uses existing
neutral surface and ink tokens; fact-specific warnings retain warning colors.
The mock photo is an extracted frame from the existing user-owned IMG_0003.MOV,
not an invented shelter animal. It is demonstration media only. No real dog
record, profile photograph or backend data is replaced.

Public hero photo is 400px tall on desktop and 280px on mobile. The sidebar
track is 280px on desktop and stacks below facts on mobile.
