# Dr. Hunter 8-Camera Shoot — Prep Checklist (July 27)

Purpose: capture reference footage of Dr. Hunter (Oregon) performing the physical exam — proper technique AND deliberately improper technique, narrated — to train and evaluate the CME analysis AI. This footage becomes the ground-truth library the software compares defense CMEs against.

The single most important rule: **narrate everything**. The software analyzes audio and video together. Every time Dr. Hunter says "this is the correct way to test X" or "this is what defense doctors do wrong — watch the elbow," that sentence becomes a training label attached to that exact moment of video. Silent footage is one-tenth as useful.

---

## 1. Camera setup (8 angles)

| # | Angle | Why the AI needs it |
|---|-------|---------------------|
| 1 | Wide master — full room, both people always in frame | Establishes who is where; catches doctor leaving, phone use, patient waiting |
| 2 | Front of patient, chest-up | Facial expression, distress, eye contact, cranial nerve tests |
| 3 | Behind/over doctor's shoulder | What the doctor actually sees and touches; hand placement |
| 4 | Side profile left | ROM in the sagittal plane (flexion/extension) |
| 5 | Side profile right | Same, opposite side; catches asymmetric technique |
| 6 | Close-up on hands/instrument | Goniometer/inclinometer readings, reflex hammer strikes, resistance in strength tests |
| 7 | Low angle on lower body | Gait, Romberg, Babinski, foot/ankle work, leg length |
| 8 | Overhead or high corner | Rotation ROM (looks straight down on cervical/thoracic rotation), overall body position |

Practical notes:

- Lock exposure and focus; no auto-hunting mid-test.
- All cameras record continuously — do not stop/start per test. Sync with a single loud clap at the start (visible on all 8 angles).
- Timestamps: if cameras can burn in a timecode, do it. Otherwise the clap is our sync point.
- Audio: one good lav mic on Dr. Hunter feeding at least one camera. Room audio alone will lose the narration.
- Lighting: even, no backlit windows behind the exam table.

## 2. Shooting protocol per test

For EVERY test, run this exact sequence:

1. **Announce**: "Next test: [exact name], [body part], [what it detects]." (e.g., "Next test: Hoffmann sign, cervical myelopathy screen.")
2. **Proper version**: perform it correctly at normal speed, narrating each step and what a positive/negative result looks like.
3. **Proper version, slow**: repeat at half speed, calling out hand position, patient position, instrument reading.
4. **Improper version(s)**: perform the common defense-CME shortcuts, narrating exactly what is wrong: "This is what defense examiners do — testing through clothing / no goniometer / only one plane / two seconds instead of holding — and it's wrong because..."
5. **Close**: "End of [test name]." (Gives the software clean segment boundaries.)

The proper/improper pairing is the core training signal — the software learns to tell them apart only if it sees both, labeled by voice.

## 3. Test coverage list

### Range of motion — every plane, every region (Refs B, C)

- Cervical: flexion, extension, left/right lateral bending, left/right rotation — with inclinometer/goniometer AND deliberately without (improper).
- Lumbar/thoracic: flexion, extension, lateral bending, rotation.
- Shoulder: forward flexion, abduction, internal/external rotation.
- Elbow, wrist, hip, knee, ankle: full planes per AMA guides.
- Improper variants to stage: eyeballing without instrument, not isolating the segment, stopping at first complaint without noting degrees, testing through bulky clothing.

### Named neurologic tests (Refs D–K, N, Y)

- Hoffmann sign, Babinski sign, clonus.
- Romberg (eyes open then closed, timed, arms position narrated).
- Straight leg raise (angle called out; sitting vs supine discrepancy — do both).
- Deep tendon reflexes: biceps, triceps, brachioradialis, patellar, Achilles — proper hammer strike vs a lazy tap.
- Manual muscle testing, 5/5 scale: each major muscle group, showing real resistance vs the improper "handshake" version.
- Sensory exam: dermatomal light touch/pinprick — on skin (proper) vs through clothing (improper — we already flag this).
- Coordination: finger-to-nose, heel-to-shin, rapid alternating movements.
- Cranial nerves II–XII, especially eye tracking, saccades, convergence, head thrust.
- Gait: normal, heel, toe, tandem — patient in suitable clothing, full body in frame (camera 7).

### Orthopedic special tests (Refs A, K, L, U, W)

- Spurling's, shoulder impingement battery (Neer, Hawkins), knee (McMurray, Lachman, drawer), Tinel/Phalen at the wrist.
- Palpation methodology: narrate what is being palpated and expected findings.
- Waddell's signs — perform all five and narrate what over-reading them looks like.
- Leg length measurement, proper landmark to landmark.

### Exam conduct / behavior (the "was the doctor fair" layer)

Stage short scenes of each, clearly announced as staged:

- Doctor checking phone mid-exam; doctor turned away writing while patient talks.
- Rushed exam: full "exam" in under two minutes, narrated afterward as improper.
- Patient in street clothes vs gowned — same tests both ways, so the model learns why attire matters.
- Patient distress moment (acted) and the correct doctor response.
- Doctor never touching the patient ("visual-only exam") — narrate why that is inadequate.

## 4. Narration cheat-sheet for Dr. Hunter

Phrases that map directly to training labels — use them verbatim where natural:

- "This is the CORRECT technique for ___."
- "This is IMPROPER — defense examiners commonly ___ — it is wrong because ___."
- "I am using a [goniometer/inclinometer]; the reading is ___ degrees."
- "A positive finding would look like ___; this patient is negative/positive."
- "Note the patient is [gowned / in street clothes] — this matters because ___."
- "This test cannot be done through clothing because ___."
- "End of [test name]."

Also valuable: 2–3 minutes at the end of each body region where he free-talks about what he sees defense CME doctors skip or fake for that region.

## 5. How this footage trains the AI (what happens after the shoot)

1. Footage is frame-sampled and each segment is labeled using Dr. Hunter's own narration (test name, proper/improper, instrument, attire) — the announce/close phrases give us clean boundaries.
2. Labeled clips extend the golden set (`tests/fixtures/golden_set/`), which is the exam the AI must pass: we run the vision model against it and measure whether it identifies the test, technique quality, and behavior signals correctly (`scripts/eval_cme_vision.py`).
3. Proper/improper pairs become the reference standard the claim verifier cites: "Report says cervical ROM was measured; video shows no inclinometer — compare Dr. Hunter reference technique at [link]."
4. His narrated "what defense doctors do wrong" commentary is parsed into the methodology knowledge base alongside the reference PDFs already ingested.

## 6. Logistics checklist

- [ ] 8 cameras + tripods, charged, empty cards (40-min continuous × 8 ≈ plan 256GB+ total)
- [ ] Lav mic on Dr. Hunter + backup recorder
- [ ] Goniometer, inclinometer, reflex hammer, pinwheel/monofilament, tape measure
- [ ] A "patient" (staff/volunteer) who can be gowned; bring both gown and street clothes
- [ ] Printed copy of section 3 as the shot list; check off each test as captured
- [ ] Sync clap at start of every card change
- [ ] After shoot: copy all cards to one drive, folder per camera, no renaming
