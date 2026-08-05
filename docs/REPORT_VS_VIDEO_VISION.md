# Report vs Video — Product Vision (Tim / deposition)

**Status:** Target architecture (May 2026)  
**Problem:** Current HTML report leads with patient distress, eye contact, and 642 “not observing patient” rows. Tim pushed back. That is **supplemental** behavior evidence, not the core product.

## What counsel actually needs

For **every test the doctor documents** in the defense PDF:

1. **Exact report citation** — page, section, verbatim quote  
2. **What video shows** at timestamp(s) — test performed or not, technique quality  
3. **Deposition line** — “Doctor, page 2 of your report says X; at 14:22 the video shows Y”  
4. **Click timestamp** → scroll to video, play clip  

### Example (Osborne report, page 2)

| Report quote | Desired video finding | Deposition hook |
|--------------|----------------------|-----------------|
| “Deep tendon reflexes: **0/4 throughout**” | No hammer in 2617 frames; or hammer but no strike | “You graded DTR 0/4 — show me where you used a reflex hammer on video.” |
| “Rhomberg’s testing is **negative**” | No Romberg stance observed | “You documented Romberg — point to it on the video.” |
| “No **long tract signs**” | No Hoffmann/Babinski maneuver tagged | “You ruled out Babinski — where on video?” |
| “Cervical: ROM **normal** aside from mild sidebending limits” | ROM frames with **no goniometer**; only 2 planes visible | “You said normal ROM — video shows no inclinometer and incomplete planes.” |
| “Motor: **5/5 throughout**” | Spot-check MMT through clothing, not 24 muscle groups | “5/5 throughout — video shows abbreviated testing through a jacket.” |
| “Sensory: **pinprick** … upper and lower extremities” | Sensory through clothing at 15:12 | “Pinprick through clothing is not standard.” |

## What we built wrong

| Output | Why it misses the mark |
|--------|------------------------|
| 354 / 136 “test” ledger rows | Frame tags (palpation spam), not report line items |
| TOP FINDINGS: patient distress | Tim cares about **report lies/omissions**, not crying during history |
| TIMESTAMPED LOG: palpation × 298 | Not tied to **what the report claims** |
| Category claims (`strength: 5/5 throughout`) | Too coarse — no planes, no Babinski, no DTR grading |

## Target pipeline

```
Doctor PDF
    → atomic_claims.json   (one row per documented test + page/quote)
    → vision frames        (tag: test_name, planes, instrument, clothing)
    → claim_verifier       (per claim: supported | contradicted | incomplete | not_shown)
    → Tests tab UI         (report quote | verdict | technique gap | timestamps)
```

### Atomic claim schema (`claims_atomic.json`)

```json
{
  "claim_id": "dtr_0_4",
  "test_name": "Deep tendon reflexes",
  "report_page": 2,
  "report_section": "Neurologic examination",
  "report_quote": "Deep tendon reflexes: 0/4 throughout.",
  "technique_dimensions": ["hammer_visible", "patellar", "achilles", "biceps", "brachioradialis"],
  "video_verdict": null,
  "video_timestamps": [],
  "deposition_prompt": "You documented 0/4 DTR throughout — identify the timestamp where you used a reflex hammer."
}
```

## Report output priority (new order)

1. **Deposition crosswalk** — report claim vs video (primary)  
2. **Technique deficiencies** — goniometer, clothing, street shoes  
3. **Behavior / distress** — appendix only, not TOP FINDINGS  

## Implementation milestones

| Milestone | Deliverable |
|-----------|-------------|
| **B1** | `extract_report_claims.py --atomic-out claims_atomic.json` with page numbers |
| **B2** | Vision prompts tag Hoffmann, Babinski, DTR hammer, Romberg, ROM planes |
| **B3** | `claim_verifier` runs on atomic claims; UI shows deposition prompts |
| **B4** | Regenerate `STANDARD_CME_REPORT.html` — crosswalk first, distress last |

## Osborne source report

`cme_projects/osborn_2021_03/Expert_-_Dr._Brett_Osborn_Report__3.11.21_CME#2.txt`  
Page 2 neurologic block contains the test claims Tim will cross-examine.
