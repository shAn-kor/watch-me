# PRD: Watch Me! (v1.3, 2026-10-28)

Source plan: SERVICE.md (v0.3). Evidence: research/adoption-pain-points.md.
Status words: **R1** = first release (hackathon build, due 2026-11-05 11:00
KST). **R2** = later. "TBD" = needs a decision or a measurement.

Changes in v1.3: REV-5 acceptance criterion says the public API returns HTTP 404 for a hidden profile and the page says "not available" (ADR-0040).

Changes in v1.2 (ADR review): fact status has no "published"; safety
controls removed from the cut list; QA-4 R1 wording; 404 for unpublished;
upload-only capture.

Changes from v1.0 (red-team review, 2026-10-28): safety banner and
per-fact clip length; Q&A rebuilt as fact-ID selection with server-rendered
answers and an adversarial test set; R1 cut to one seeded path; numeric
timestamp bar with a segment fallback; confirm only after the clip plays;
"known concerns" field; no third parties in frame; G1 restated as a
hypothesis; Korea scope stated honestly.

## 1. Summary

Watch Me! turns short shelter clips into a dog profile where every behavior
claim links to the clip moment that shows it. Volunteers film and talk; the
AI drafts facts with timestamps; a human watches and confirms each fact;
adopters tap a fact to watch the evidence and ask questions that are
answered only with confirmed facts.

The core is video-to-timestamped-evidence. The Q&A is a constrained lookup
over confirmed facts, not a free chat.

## 2. Goals and non-goals

Goals:

- G1 (hypothesis, unmeasured). A volunteer makes a behavior-rich listing in
  under 15 minutes per dog. No baseline exists (research file: "time spent
  per listing: no source found"). Measure in R1; do not claim it before.
- G2. Every published behavior fact has clip evidence or is marked
  narration-only.
- G3. Adopters get a fact-cited answer or "not observed yet" for every
  question.

Non-goals:

- Not a behavior or safety assessment. Clips are samples. Short
  observations do not reliably predict aggression, food guarding, or
  separation problems (research file, Australian study of 123 dogs).
- No personality scores or trait labels.
- No health assessment or medical advice.
- No adoption applications, payments, or matching.
- No search or browse screen.
- No native mobile app (mobile web only).

## 3. Users and roles

| Role               | Who                        | Can do                                            | Rel |
| ------------------ | -------------------------- | ------------------------------------------------- | --- |
| Staff              | Shelter employee           | Publish, unpublish, mark adopted, delete, confirm | R1  |
| Volunteer / foster | Member                     | Film; confirm facts from own sessions             | R1  |
| Adopter            | Public visitor, no account | View profile, play clips, ask                     | R1  |
| Org admin          | Shelter manager            | Manage members                                    | R2  |
| Platform operator  | Watch Me! team             | Approve organizations                             | R2  |

R1 runs with one seeded organization, one staff account, and one volunteer
account.

## 4. Functional requirements

Format: ID, requirement, release, acceptance criteria (AC).

### 4.1 Organizations and members

| ID    | Requirement                                                                                                                                                              | Rel | AC                                                              |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --- | --------------------------------------------------------------- |
| ORG-0 | One organization and its members are seeded by config.                                                                                                                   | R1  | The seeded org shows on profiles without a "verified" badge.    |
| ORG-4 | Members accept a consent notice for their face and voice in clips.                                                                                                       | R1  | A member cannot upload before accepting.                        |
| ORG-1 | Organization sign-up with proof: US EIN checked against the IRS tax-exempt list; Korea registration number of an animal protection center or registered private shelter. | R2  | Org stays "pending" until checked; pending orgs cannot publish. |
| ORG-2 | Operator approves or rejects; approved orgs get a verified badge.                                                                                                        | R2  | Badge only after ORG-1 check passes.                            |
| ORG-3 | Admin invites members by link and assigns a role.                                                                                                                        | R2  | Link expires after 7 days.                                      |

### 4.2 Capture (creator side)

| ID    | Requirement                                                                           | Rel | AC                                                                                                   |
| ----- | ------------------------------------------------------------------------------------- | --- | ---------------------------------------------------------------------------------------------------- |
| CAP-1 | Member creates a dog with name, sex, age estimate, size, photo.                       | R1  | Dog appears in the dog list.                                                                         |
| CAP-2 | Dog list shows situation coverage per dog.                                            | R1  | Same rule as PUB-1.                                                                                  |
| CAP-3 | Member starts a session and picks situations (section 5.2).                           | R1  | Session stores situations and date.                                                                  |
| CAP-4 | Member uploads clips with audio.                                                      | R1  | MP4/MOV including iPhone HEVC; up to 2 minutes and 200 MB per clip; up to 3 clips per session in R1. Phones record through the file picker's camera option; no in-page recorder in R1. |
| CAP-7 | Capture rules screen before filming: only the dog and the consenting member in frame. | R1  | Shown on every new session.                                                                          |
| CAP-8 | Error states: unsupported file, too large, upload failed, processing failed.          | R1  | Each shows a cause and a retry; no silent failure.                                                   |
| CAP-9 | Server transcodes clips to H.264 MP4 for playback.                                    | R1  | Range playback works on iOS Safari and Android Chrome.                                               |
| CAP-5 | Resumable upload on weak connections.                                                 | R2  |                                                                                                      |
| CAP-6 | Photograph a vaccination record.                                                      | R2  | See AI-4.                                                                                            |

### 4.3 Review and publish

| ID     | Requirement                                                                                                                            | Rel | AC                                                                                  |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------- | --- | ----------------------------------------------------------------------------------- |
| REV-1  | One card per draft fact with its clip range playing inline.                                                                            | R1  | The card starts the clip at the fact's start time.                                  |
| REV-2  | Member confirms, edits, or deletes each draft fact. "Confirm" is enabled only after the clip range has played to its end.              | R1  | Server rejects a confirm with no completed playback event.                          |
| REV-3  | Member adds a fact by hand and attaches a clip range.                                                                                  | R1  | No clip range means source "staff note".                                            |
| REV-4  | Volunteers confirm facts only from their own sessions.                                                                                 | R1  | Server rejects other confirmations.                                                 |
| REV-9  | Pre-publish checklist: (a) no people other than consenting members in any clip, (b) "known concerns" filled in or marked "none known". | R1  | Publish stays disabled until both are checked.                                      |
| REV-5  | Staff publishes and gets a public link.                                                                                                | R1  | Link works without sign-in; the public API returns HTTP 404 for a hidden profile; the page says "not available".                 |
| REV-6  | Staff unpublishes, marks adopted, or deletes a dog.                                                                                    | R1  | Adopted: profile hidden, clips kept. Deleted: clips and facts removed from storage. |
| REV-10 | Each fact records whether it is AI-drafted unchanged or human-edited.                                                                  | R1  | Stored and counted for the metric in section 8.                                     |
| REV-7  | Edit history; deleting a published fact needs a reason.                                                                                | R2  |                                                                                     |
| REV-8  | Bilingual profile (English/Korean).                                                                                                    | R2  |                                                                                     |

### 4.4 Public profile (adopter side)

| ID    | Requirement                                                                                                                                        | Rel | AC                                           |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------- | --- | -------------------------------------------- |
| PUB-0 | Fixed banner: "These clips are short samples. They are not a behavior or safety assessment. Meet the dog and talk to the shelter before adopting." | R1  | Visible above the facts on every profile.    |
| PUB-1 | Header: photo, name, age, size, location, and coverage stated as "clips in n of 8 situations", with clip count and total seconds per situation.    | R1  | Numbers match stored clips.                  |
| PUB-2 | Facts grouped by situation; each shows behavior, clip length (e.g. "1 clip, 9 s"), observation date, source, and "confirmed by <role>".            | R1  | No unconfirmed fact appears.                 |
| PUB-3 | Tapping a fact plays its clip range.                                                                                                               | R1  | Playback starts at the range start.          |
| PUB-4 | "Not observed yet" list shows every situation with no clip.                                                                                        | R1  | List equals 8 situations minus covered ones. |
| PUB-8 | "Known concerns" from the shelter, shown above the facts.                                                                                          | R1  | Shows "none known" when marked so.           |
| PUB-9 | Situation 8 (children or cats) facts carry "ask the shelter about an in-person meeting".                                                           | R1  | Only staff can confirm situation 8 facts.    |
| PUB-7 | Contact block uses the shelter's own channel.                                                                                                      | R1  | No in-app application form.                  |
| PUB-5 | Facts older than 90 days show "may be outdated".                                                                                                   | R2  | Threshold is a setting.                      |
| PUB-6 | "This does not match the clip" report to a staff queue.                                                                                            | R2  |                                              |

### 4.5 Evidence-only Q&A

| ID   | Requirement                                                                                                                                            | Rel | AC                                                                                                                                                             |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| QA-1 | Adopter types a question on the profile.                                                                                                               | R1  | Limit per IP and per cookie (10 per hour); global daily cost cap stops Q&A when reached.                                                                       |
| QA-2 | The model returns only a list of fact IDs (or none) from this dog's confirmed facts. The server renders the answer from those facts' text, with links. | R1  | The model never writes answer prose. Any ID not in the dog's confirmed facts is dropped; an empty list renders "Not observed yet".                             |
| QA-4 | Health questions render "Ask the shelter's vet". Adding transcribed records to the answer waits for AI-4 (R2).                                                         | R1  | No diagnosis wording is possible because the server renders all text.                                                                                          |
| QA-7 | Adversarial test set of at least 50 questions: no evidence, paraphrased trait claims, child-safety questions, health questions, prompt injections.     | R1  | Bar: 0 answers cite a fact outside the dog's confirmed set. Target: at least 95% of no-evidence questions return "Not observed yet". Report the measured rate. |
| QA-3 | "Ask the shelter to film this" sends the question to a request inbox.                                                                                  | R2  |                                                                                                                                                                |
| QA-5 | Personal data removed before a question reaches staff.                                                                                                 | R2  | Needed only with QA-3.                                                                                                                                         |
| QA-6 | Request inbox grouped by situation.                                                                                                                    | R2  |                                                                                                                                                                |

### 4.6 AI processing

| ID   | Requirement                                                                                                                  | Rel | AC                                                                                                                                                                                                                                                                      |
| ---- | ---------------------------------------------------------------------------------------------------------------------------- | --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AI-1 | Transcribe narration with timestamps using Muse Voice Transcribe.                                                            | R1  | Korean and English narration both work.                                                                                                                                                                                                                                 |
| AI-2 | Draft facts from clips plus narration transcript using Muse Spark: situation, behavior text, clip ID, start and end, source. | R1  | Schema-valid output (section 5.1); invalid output retried once, then CAP-8 error. Timestamp bar: at least 80% of cited ranges contain the behavior, hand-checked on a 10-clip spike set. Below the bar: switch to fixed 10 s segments, and the model cites segment IDs. |
| AI-3 | Wording check on drafts: banned-word list plus a model pass that flags trait claims.                                         | R1  | Flagged drafts show a warning on the review card. The human reviewer is the main guard; the check is not a guarantee.                                                                                                                                                   |
| AI-8 | Prompt isolation: narration and adopter questions are passed as data, never as instructions.                                 | R1  | Injection cases in QA-7 pass.                                                                                                                                                                                                                                           |
| AI-4 | Transcribe a vaccination record photo into a table.                                                                          | R2  | Member confirms; no interpretation.                                                                                                                                                                                                                                     |
| AI-5 | Face blur for people in clips (SAM 3.1 candidate).                                                                           | R2  | Move to R1 only if the spike finishes early.                                                                                                                                                                                                                            |
| AI-6 | Highlight clip from confirmed fact ranges.                                                                                   | R2  |                                                                                                                                                                                                                                                                         |

## 5. Content rules

### 5.1 Fact schema

| Field        | Type                                      |
| ------------ | ----------------------------------------- |
| situation    | one of the 8 situations                   |
| behavior     | short text, observable verbs              |
| evidence     | list of {clip_id, start_s, end_s}         |
| source       | clip / narration / staff_note             |
| observed_on  | date of the session                       |
| status       | draft / confirmed / deleted ("published" is a dog state) |
| origin       | ai_unchanged / human_edited / human_added |
| confirmed_by | member ID and role, timestamp             |

### 5.2 Situations

1. Meeting a new person. 2. Handling. 3. Leash walk. 4. Meeting another
   dog. 5. Food and toys. 6. Alone time. 7. Indoors and rest. 8. Children or
   cats (only when actually observed; staff confirm only).

### 5.3 Wording rules

- Describe what can be checked in the clip ("barked 3 times", "rolled onto
  back").
- Banned: trait labels and judgments ("aggressive", "friendly", "anxious",
  "good with kids", "calm dog"), and paraphrased trait claims ("doesn't
  mind being grabbed"). The list lives in config and grows.
- Narration-only facts say "said by volunteer, not in clip".
- Never fill an uncovered situation with a guess.

## 6. Non-functional requirements

| ID    | Requirement                                     | Target                                                                                                                              | Rel                |
| ----- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| NFR-1 | Processing time for one session (up to 3 clips) | Under 5 minutes (measure in spike)                                                                                                  | R1                 |
| NFR-2 | AI cost per listing                             | Measure in spike; R1 must fit the US$150 hackathon credit. Long-term target under US$0.50 with open-weight models for routine work. | R1                 |
| NFR-3 | Devices                                         | Mobile web on current iOS Safari and Android Chrome                                                                                 | R1                 |
| NFR-4 | Languages                                       | R1: English UI; Korean or English narration. Korean UI and bilingual profiles: R2                                                   | R1                 |
| NFR-5 | Privacy                                         | Clips private until published; adopted or deleted dogs never public; training use only with opt-in                                  | R1                 |
| NFR-8 | Deletion                                        | Staff deletes a dog or a clip; storage copies removed                                                                               | R1                 |
| NFR-9 | Legal                                           | Banner (PUB-0) and a short terms page. Legal review (US state biometric laws, Korea PIPA) before real launch                        | R1 page, R2 review |
| NFR-6 | Accessibility                                   | Captions from narration transcript (R1); WCAG 2.2 AA audit (R2)                                                                     | R1/R2              |
| NFR-7 | Availability                                    | Best effort; no SLA                                                                                                                 | R1                 |

## 7. Release 1 scope

One path, end to end:

1. Day 1: timestamp spike (AI-1, AI-2 on 10 clips; measure the 80% bar,
   time, and cost). Choose free timestamps or 10 s segments.
2. Seeded org and members (ORG-0, ORG-4).
3. Capture and processing (CAP-1 to CAP-4, CAP-7 to CAP-9, AI-1 to AI-3,
   AI-8).
4. Review and publish (REV-1 to REV-6, REV-9, REV-10).
5. Public profile (PUB-0 to PUB-4, PUB-7 to PUB-9).
6. Q&A (QA-1, QA-2, QA-4, QA-7).

Cut first if time runs short (in this order): REV-10, CAP-2, QA-1
per-cookie limit (keep the cost cap). Safety controls (PUB-0, PUB-9, REV-2,
REV-9, QA-2) are never cut.

Korea scope: the R1 build is English-facing. Korea evidence (health and
vaccination records, 35.3%) is served by AI-4 in R2. Do not claim Korea
features that R1 does not have.

## 8. Success metrics

- Timestamp accuracy: share of cited ranges that contain the behavior.
- Draft acceptance: AI-unchanged confirmed facts / all drafts. A very high
  rate with short review time signals rubber-stamping.
- Q&A: QA-7 pass rates.
- Volunteer time per listing (measures G1; no baseline yet).
- Share of published facts with clip evidence (G2).

## 9. Risks and open questions

| Risk / question                                                   | Plan                                                                                                                |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Adopters read facts as a safety guarantee; a bite after adoption. | PUB-0 banner, per-fact clip length, known concerns, staff-only situation 8, terms page; legal review before launch. |
| Muse Spark timestamps unreliable.                                 | Day 1 spike with the 80% bar; 10 s segment fallback.                                                                |
| Q&A drifts into claims or follows injected instructions.          | Model selects fact IDs only; server renders text; QA-7 test set.                                                    |
| Volunteers confirm without watching.                              | REV-2 playback gate; draft acceptance metric.                                                                       |
| Shelters film only good moments.                                  | Clip count and seconds per situation; known concerns field.                                                         |
| Third parties or minors in clips.                                 | CAP-7 rules, REV-9 checklist, deletion (NFR-8); face blur R2.                                                       |
| Shelter workload: filming may cost more time than a text bio.     | G1 is a hypothesis; measure before claiming.                                                                        |
| Fake organizations.                                               | R1 seeded only; R2 proof check (ORG-1).                                                                             |
| Hackathon anti-project "simple RAG".                              | Lead with video-to-timestamped-evidence; Q&A is a constrained lookup.                                               |
| "Watch Me" name collisions and trademark.                         | Check App Store, USPTO, KIPRIS before public launch.                                                                |
| Listing site APIs (animal.go.kr, Petfinder).                      | R2; verify availability.                                                                                            |
