# CME Video Analysis Software - Dorothy's Requirements

## Source: Emails from Dorothy Clay Sims (Feb 4 & Feb 11, 2026)

---

## CRITICAL REQUIREMENTS CHECKLIST

### 1. CLAIM VS REALITY (Most Important)
- [ ] What the report claims vs what actually happened in exam
- [ ] Whether report misrepresents what was said in transcript
- [ ] Find objective findings doctor left out
- [ ] Find objective findings doctor misrepresented

### 2. DOCTOR BEHAVIOR
- [ ] Determine if doctor was rude
- [ ] Didn't observe patient while having them do ROM/tests
- [ ] Top 10-20 egregious behaviors (at beginning of report)
- [ ] How many times doctor was interrupted + WHERE in video

### 3. PATIENT OBSERVATIONS
- [ ] If patient cried - document each time
- [ ] If patient was confused - document each time
- [ ] Patient distress indicators

### 4. EXAMINATION TIMING
- [ ] Length of physical exam
- [ ] Timestamp each test/segment

### 5. CRANIAL NERVES
- [ ] Were ALL cranial nerves assessed properly?
- [ ] Which specific cranial nerves were NOT assessed?
- [ ] Compare claimed findings vs actual testing observed

### 6. MENTAL STATUS TESTING
- [ ] Identify which test was given (MOCA vs Folstein)
- [ ] Document actual score observed
- [ ] Compare to doctor's estimated/reported score
- [ ] Flag discrepancies

### 7. RANGE OF MOTION
- [ ] Was ROM tested?
- [ ] Was ROM limited?
- [ ] What was actual ROM observed?
- [ ] Was goniometer used for objective measurement?

### 8. BODY PART BREAKDOWN
- [ ] Break down analysis by body part:
  - Neck/Cervical
  - Shoulder
  - Upper extremity (arm, elbow, wrist, hand)
  - Back/Thoracic/Lumbar
  - Hip
  - Lower extremity (leg, knee, ankle, foot)
  - Neurological

### 9. DR. HUNTER INTEGRATION
- [ ] Train on Dr. Hunter's references (thousands sent)
- [ ] Train on Dr. Hunter's YouTube videos
- [ ] Show "how it should have been done" vs "how doctor did it"
- [ ] Insert references in report for lawyer

### 10. PROJECT MANAGEMENT
- [ ] Save all projects by patient name
- [ ] Save redlined report with each project for verification
- [ ] Track which case analysis came from
- [ ] Ensure software watches ENTIRE video (not missing segments)

---

## DOROTHY'S CONCERNS

1. **Missing segments**: "I think before you do the final training you need to know if the software is even actually watching the entire video or if it's missing segments"

2. **Verification needed**: Analysis may have left out things doctor actually did (like cranial nerves)

3. **Source tracking**: Need to verify which case analysis came from

---

## OUTPUT FORMAT REQUIREMENTS

1. Top 10-20 egregious behaviors at BEGINNING of report
2. Break down by body part
3. Include references for lawyer
4. Save with patient name
5. Include redlined report for verification

---

## IMPLEMENTATION STATUS

| Requirement | Status | Notes |
|-------------|--------|-------|
| Claim vs Reality | ✅ Implemented | In comprehensive analyzer |
| Doctor Rudeness | ✅ Implemented | In behavior analyzer |
| Not Observing Patient | ✅ Implemented | Eye contact tracking |
| Exam Length | ✅ Implemented | Timing analysis |
| Patient Crying | 🔄 Needs Enhancement | Add specific detection |
| Patient Confusion | 🔄 Needs Enhancement | Add specific detection |
| Interruption Count + Location | ✅ Implemented | With timestamps |
| Top 10-20 Egregious | ✅ Implemented | worst_moments list |
| Transcript Misrepresentation | 🔄 Needs Enhancement | Compare transcript to report |
| Cranial Nerve Checklist | 🔄 Needs Enhancement | Specific CN tracking |
| Mental Status (MOCA/Folstein) | ❌ Not Implemented | Need to add |
| ROM Measurement | ✅ Implemented | Goniometer detection |
| Body Part Breakdown | 🔄 Needs Enhancement | Add structured output |
| Dr. Hunter References | ❌ Not Implemented | Need training data |
| Project Saving by Name | ❌ Not Implemented | Need to add |
| Video Coverage Check | ❌ Not Implemented | Need to verify full coverage |
