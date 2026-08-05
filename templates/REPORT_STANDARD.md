# CME Analysis Report Standard

This document defines the standard format for all CME video analysis reports.

## Required Sections (in order)

### 1. Header
- Patient Name, DOB
- Examiner Name, MD
- Date of CME
- Date of Injury
- Video Length
- Frames Analyzed

### 2. CROSS-EXAMINATION FINDINGS (Red Box)
Numbered, litigation-ready findings, ranked most-damning first:

```
CROSS EXAMINATION #1: Doctor stated in his report that he performed the Babinski test.
FACT: What was performed could barely qualify as a Babinski — it was hardly one
plane of motion. See 22:13 of the video.
```

Each finding MUST have:
- The doctor's specific written claim (quoted verbatim with page reference when available)
- A "FACT:" rebuttal describing what the video actually shows
- A specific video timestamp citation (not_shown findings cite the exam window)

Inclusion test (enforced in code via `passes_materiality_gate`): does this
contradict or undercut a specific claim in the doctor's written report,
provable by timestamped video/audio evidence?

Ranking (enforced via `cme_egregious_ranking.compute_egregious_score`):
contradictions > tests never performed on video > tests performed but omitted
from the report > unverifiable measurements (ROM without goniometer) >
technique gaps.

HARD-BANNED from findings: name spellings, transcription artifacts,
administrative details, recording quality, and demeanor/tone complaints that
carry no exam substance.

### 3. EXAMINATION TIMELINE OVERVIEW
Table with:
- Physical Exam Window (start - end timestamps)
- Total Hands-On Duration
- Goniometer/Inclinometer Used (YES/NO)
- Doctor Eye Contact percentage

### 4. DOCTOR BEHAVIOR ANALYSIS
- Attention progress bar with percentage
- Table of timestamps when doctor NOT observing patient
- Behavioral Assessment Summary (Patient Attention, Examination Thoroughness, Measurement Methodology)

### 5. TIMESTAMPED EXAMINATION LOG
- Scrollable dark log showing every test with timestamp
- Format: [MM:SS] Body Part: Description...
- Grouped by test type (Inspection, Palpation, ROM, Strength, Reflex, etc.)

### 6. CLAIM VS. VIDEO REALITY
Side-by-side comparison boxes for each body region:
- Cervical Spine ROM
- Right Shoulder ROM
- Left Shoulder ROM  
- Neurological Examination
- (Add more as needed based on claims)

Each comparison includes:
- REPORT CLAIMS box (gray)
- VIDEO REALITY box (red tint) with timestamps

### 7. BODY PART EXAMINATION TIMELINE
Table with columns:
- Body Part
- First Examined (timestamp)
- Last Examined (timestamp)
- Tests Performed
- Frame Count

### 8. EXAMINATION COMPONENTS OBSERVED
Table with columns:
- Test Type
- Frames Observed
- First Timestamp
- Last Timestamp

### 9. PATIENT DISTRESS DOCUMENTATION
Warning box with table:
- Timestamp
- Observation description

### 10. STANDARD OF CARE REFERENCES
Info boxes for:
- Range of Motion Measurement (AMA Guides, goniometer requirements, normal values)
- Neurological Examination (complete exam components)
- Comprehensive Examination Duration (expected time for complex patients)

### 11. EXECUTIVE SUMMARY (Dark Blue Box)
Numbered list of key findings with percentages and counts

### 12. Footer
- Report Generated date
- Analysis Method (frame count, interval)
- Video Duration

## Timestamp Format
All timestamps should be in `MM:SS` format for future video linking capability.

## Template Location
`/templates/STANDARD_CME_REPORT_TEMPLATE.html`

## Example Report
`/cme_projects/Green_Tracy/GREEN_CME_COMPLETE_REPORT.pdf`
