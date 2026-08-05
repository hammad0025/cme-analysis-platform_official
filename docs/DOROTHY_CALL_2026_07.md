# Dorothy Call Notes — July 1, 2026

Attendees: Dorothy, Hammad
Topic: CME analysis software — current state, deliverables, and prep for the July 27 Dr. Hunter shoot.
Next call: **Wednesday, July 8 at 8:00 PM ET (5:00 PM PT)**.

This doc backs the confirmation email. Everything below reflects what was discussed and agreed on the call.

---

## Decisions

1. **Cross-examination format in the report.**
   The "Report vs. video" discrepancy section will be restructured into a true cross-examination format: each finding leads with a leading question, followed by the doctor's exact report statement (with page number), the video finding with a clickable timestamp link, and supporting literature references. This is the format Tim described — set up the question, then present the evidence.

2. **Literature references become online links.**
   Dr. Hunter's reference PDFs are already parsed into the system's knowledge base, but the report currently cites local filenames. The report will instead link to the online source (PubMed / NCBI / DOI / publisher abstract) so lawyers can click through from the PDF report. Perplexity research citations (URLs) will also be surfaced in the report.

3. **Video deep-links from the report.**
   Timestamps in the PDF/HTML report will be clickable hyperlinks. Clicking one opens the web app's session page and jumps the video player to that exact moment (e.g., a 40-minute CME opens at the 20-minute mark where the test was performed improperly). This is already working in the web app; the report links are being wired up.

4. **Sample report from Audrey's CME.**
   Hammad will run the CME video(s) Audrey sent through the software and deliver the generated report plus the interactive session link to Dorothy and Tim, so Oregon's manual analysis can be compared side-by-side against the software's output. Target: **within two days of this call** (by July 3).

5. **Billing / accounts.**
   CME runs now go through Tim's corporate Perplexity (enterprise) account, so there is no personal-account billing holdup on running multiple CMEs.

6. **HIPAA / data protection (discussed, no change needed).**
   The platform runs on AWS; PII is anonymized (AWS Macie) before any data reaches an AI provider. Enterprise licenses (Perplexity, and enterprise-tier LLM accounts) contractually prohibit providers from training on our data. Case data stays internal.

## Action items

| # | Item | Owner | Due |
|---|------|-------|-----|
| 1 | Send confirmation email of this call (Dorothy to save it) | Dorothy (send), Hammad (acknowledge) | ASAP |
| 2 | Run Audrey's CME through the software; send sample report + session link to Dorothy and Tim | Hammad | ~July 3 |
| 3 | Compare software report vs. Oregon's manual analysis; send feedback | Dorothy, Tim, Oregon | After #2 |
| 4 | Add cross-examination section (leading question + report quote + video link + literature refs) | Hammad | Before next call |
| 5 | Add online literature links + clickable video timestamps to the report | Hammad | Before next call |
| 6 | Meet with Tim to finalize what the July 27 shoot must capture; share prep checklist (see `docs/HUNTER_SHOOT_PREP.md`) | Hammad | Next week (before Dorothy/Tim trial window) |
| 7 | Tell Dorothy anything else Oregon should cover in the 8-camera shoot so he can prepare | Hammad | Within the next week |

## Key dates

- **July 3 (target):** Sample report from Audrey's CME delivered to Dorothy + Tim.
- **July 8, 8:00 PM ET:** Next call with Dorothy.
- **~July 15–29:** Dorothy and Tim in trial (limited availability; trial may continue to the 29th).
- **July 27:** 8-camera shoot with Dr. Hunter (Oregon) performing the physical exam — proper and improper technique, narrated. This is the primary training footage for the AI.

## July 27 shoot — what was agreed

- Eight camera angles on Dr. Hunter performing the various physical exam tests.
- Dr. Hunter narrates as he goes: what the test is, how it should be done, what defense experts do wrong, and what to look for. **Audio callouts matter** — the software captures and uses both audio and video, so explicit narration ("this is wrong because...") directly improves the AI's accuracy.
- All ROM planes by body part, named tests (Hoffmann, Babinski, Romberg, etc.), instrument use (goniometer/inclinometer), proper vs. improper versions of each test.
- Full checklist in `docs/HUNTER_SHOOT_PREP.md`.

## Current software state (as represented on the call)

- Web app is live; clicking a finding jumps the video to the relevant moment (demoed to Tim previously).
- Dr. Hunter's reference PDFs (planes of motion, body parts, test methodology) are parsed into the knowledge base.
- The gap is real-world video exposure — which the July 27 shoot addresses.
- Video-manipulation/incident-video analysis (the pool case) is a separate product track and is further from done than the CME software.
