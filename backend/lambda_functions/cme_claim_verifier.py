"""
Per-claim verifier for CME analysis (roadmap step 2 / step A1).

For each entry in a doctor's report `claims.json`, this module asks the
configured VisionClient (via its `text_analyze` text-only call) to read
summaries of the matched per-frame visual analyses and any verbal /
behavior observations, then return a structured legal verdict:

    supported, partially_supported, contradicted, not_shown,
    insufficient_evidence

The "not_shown" vs "contradicted" distinction is the legally important
one: silence in the video is not contradiction. The prompt and the
keyword-relevance helpers below are written specifically to keep that
distinction crisp.

Provider-agnostic by construction: the verifier only ever speaks to
its caller's `VisionClient` (no `if isinstance(...)` branches). The
roadmap "A2 consensus" step will invoke this verifier once per provider
and merge the verdicts; the extension hook is the `model_id` argument
on `verify_claim`, plus the fact that nothing here closes over any
specific provider.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .cme_analysis_utils import filter_medical_claims, filter_medical_claim_verdicts, is_metadata_claim_id
from .cme_evidence_quality import (
    evidence_description_for_frame,
    evidence_notes_are_usable,
    expand_claim_keywords,
    filter_frames_for_claim,
    frame_passes_quality_gates,
    notes_indicate_broll,
    select_evidence_frames_for_claim,
    summarize_video_evidence,
)


CLAIM_VERIFIER_PROMPT_VERSION = "1.2.0"

# Map atomic claim_id -> exam KB / Hunter technique keys for verifier context.
_CLAIM_HUNTER_KB_KEYS: Dict[str, List[str]] = {
    "cervical_rom": ["cervical_rom"],
    "lumbar_rom": ["lumbar_rom"],
    "long_tract_signs": ["hoffmanns_sign", "babinski_sign"],
    "romberg": ["romberg_test"],
    "gait": ["gait_observation", "tandem_gait"],
    "reflexes": ["deep_tendon_reflexes"],
    "motor_strength": ["manual_muscle_testing"],
    "sensory": ["pinprick_sensation", "proprioception"],
    "coordination": ["finger_to_nose", "heel_to_shin"],
    "cranial_nerves": ["cranial_nerve_exam"],
    "mental_status": ["mental_status_exam"],
}


@dataclass
class Evidence:
    """A single piece of evidence cited by the verifier.

    `raw_response_ref` points at the externalized raw model output under
    `comprehensive/raw/` or `behavior/raw/` so a reviewer can audit the
    original text that produced the cited frame or quote.
    """

    kind: str  # "frame" | "frame_range" | "quote" | "transcript_span" | "absence"
    frame_id: Optional[str] = None
    timestamp_sec: Optional[float] = None
    end_timestamp_sec: Optional[float] = None
    quote: Optional[str] = None
    speaker: Optional[str] = None
    raw_response_ref: Optional[str] = None
    notes: str = ""


@dataclass
class ClaimVerdict:
    """One per-claim verdict, intended to round-trip cleanly to JSON.

    `claim_payload` retains the original raw entry from `claims.json` (a
    string or a dict) so the standard report can render the full text the
    doctor wrote, not just our compact summary."""

    claim_id: str
    claim_text: str
    claim_payload: Any = None
    verdict: str = "insufficient_evidence"
    confidence: float = 0.0
    reasoning: str = ""
    evidence: List[Evidence] = field(default_factory=list)
    model_id: str = ""
    provider: str = ""
    prompt_version: str = CLAIM_VERIFIER_PROMPT_VERSION


CLAIM_VERIFIER_PROMPT = """You are an independent reviewer auditing a Compulsory Medical Examination (CME) for a legal case. The doctor was retained by the defendant's insurance company. Your job is to compare ONE specific claim from the doctor's report against the timestamped visual and verbal evidence captured from the exam video.

The five verdicts below are LEGALLY DISTINCT and must not be conflated:

- supported: The video and/or transcript directly demonstrate the test or finding the claim describes. Specific frames or quotes back the claim.
- partially_supported: Some evidence corroborates the claim but other evidence weakens it (e.g., the test was performed but technique was non-standard, or only some of the described maneuvers were observed).
- contradicted: There is direct visible or audible evidence AGAINST the claim. The patient demonstrably said or did the opposite, the test produced the opposite result on camera, or the doctor admitted the opposite. Silence is NEVER contradiction.
- not_shown: The relevant body region, test, or moment was not visible on camera (occlusion, off-screen, angle, blur), OR the question was simply never asked, OR no frame matched the claim's subject. Treat this as a SAMPLING / VISIBILITY gap, not a finding against the doctor. This is the correct verdict when you have NO relevant frames or quotes.
- insufficient_evidence: There are some relevant frames or quotes, but they are too ambiguous, too few, or too low-confidence to support any of the other four labels. Prefer this over guessing.

Hard rules:
1. If the relevant body region or test was never shown on camera or visibility was obscured, return not_shown.
2. If the patient was simply never asked the question, return not_shown. Do NOT invent contradiction from silence.
3. If matched frames disagree with each other, return partially_supported and explain which frames pulled which way.
4. Only return contradicted when there is direct visible or audible evidence AGAINST the claim.
5. Cite specific frame_ids and / or quotes you used as evidence. Do not fabricate frame_ids or quotes.
6. Confidence must reflect both the strength of the evidence AND the visibility quality of the cited frames.
7. NEVER treat transcription artifacts, name spellings or pronunciations, scheduling or administrative chatter, paperwork, greetings, or audio/recording quality as evidence for or against any claim. These are noise, not findings, and must not appear in your reasoning or evidence.
8. Tone or bedside manner alone is NOT evidence against a medical claim. Cite behavior only when it bears directly on whether the documented test was actually performed (e.g., the doctor was on the phone during the maneuver).

CLAIM UNDER REVIEW
claim_id: {claim_id}
claim_text: {claim_text}

VISUAL EVIDENCE SUMMARY (matched frames; may be empty if nothing matched)
{visual_summary}

VERBAL / BEHAVIOR EVIDENCE SUMMARY (matched transcript and behavior observations; may be empty)
{verbal_summary}

GLOBAL CONTEXT
total_frames_analyzed: {total_frames}
matched_frames_for_this_claim: {matched_frame_count}
matched_behavior_observations: {matched_behavior_count}
matched_verbal_observations: {matched_verbal_count}
{research_section}
Return a SINGLE JSON object with EXACTLY this shape (no markdown, no prose before or after):
{{
  "verdict": "supported" | "partially_supported" | "contradicted" | "not_shown" | "insufficient_evidence",
  "confidence": 0.0-1.0,
  "reasoning": "1-3 sentences explaining the verdict in clinical / evidentiary terms.",
  "evidence": [
    {{
      "kind": "frame" | "frame_range" | "quote" | "transcript_span" | "absence",
      "frame_id": "frame id used (optional)",
      "timestamp_sec": seconds (optional),
      "end_timestamp_sec": seconds (optional, for ranges),
      "quote": "exact quote (optional)",
      "speaker": "doctor" | "patient" | "unknown" (optional),
      "notes": "what this piece of evidence shows"
    }}
  ]
}}
If there is no evidence to cite, return "evidence": []. Do not invent evidence."""


def hunter_methodology_context_for_claim(claim_id: str, claim_text: str) -> str:
    """Inject Dr. Hunter proper-technique criteria and exam KB methodology for this claim."""
    from .cme_ama_rom_criteria import ama_rom_context_for_claim
    from .cme_defense_playbook import standard_of_care_context_for_claim
    from .cme_exam_knowledge_base import get_exam_by_name
    from .cme_hunter_methodology import TEST_PERFORMANCE_INDICATORS

    cid = (claim_id or "").strip().lower()
    keys = list(_CLAIM_HUNTER_KB_KEYS.get(cid, []))
    if not keys:
        for map_cid, map_keys in _CLAIM_HUNTER_KB_KEYS.items():
            if map_cid in cid or cid in map_cid:
                keys.extend(map_keys)
    if not keys:
        text = (claim_text or "").lower()
        if "hoffmann" in text or "babinski" in text or "long tract" in text:
            keys = ["hoffmanns_sign", "babinski_sign"]
        elif "romberg" in text or "rhomberg" in text:
            keys = ["romberg_test"]
        elif "cervical" in text or "neck" in text:
            keys = ["cervical_rom"]

    parts: List[str] = []
    for kb_key in dict.fromkeys(keys):
        exam = get_exam_by_name(kb_key)
        if exam:
            name = exam.get("name") or kb_key.replace("_", " ").title()
            steps = exam.get("methodology", {}).get("steps") or []
            if steps:
                parts.append(f"{name} — proper steps: " + "; ".join(str(s) for s in steps[:4]))
            duration = exam.get("methodology", {}).get("duration_seconds")
            if duration:
                parts.append(f"{name} — expected duration: ~{duration}s on video.")
        hunter = TEST_PERFORMANCE_INDICATORS.get(kb_key.replace("s_sign", "_sign").replace("hoffmanns", "hoffmann"))
        if not hunter and kb_key.endswith("_sign"):
            hunter = TEST_PERFORMANCE_INDICATORS.get(kb_key.replace("_sign", "_test"))
        if hunter:
            proper = hunter.get("proper_technique")
            if proper:
                parts.append(f"Hunter proper technique ({kb_key}): {proper}")
            errors = hunter.get("common_errors") or []
            if errors:
                parts.append(
                    "Common deficiencies to flag if visible: " + "; ".join(str(e) for e in errors[:3])
                )
    lines = (
        parts[:6]
        + standard_of_care_context_for_claim(claim_id, claim_text)
        + ama_rom_context_for_claim(claim_id, claim_text)
    )
    if not lines:
        return ""
    return "HUNTER / EXAM STANDARDS (use to judge technique; video evidence still controls verdict):\n" + "\n".join(
        f"- {p}" for p in lines
    )


def _expand_claim_keywords(claim_id: str, claim_text: str) -> List[str]:
    """Backward-compatible alias; delegates to cme_evidence_quality."""
    return expand_claim_keywords(claim_id, claim_text)


def _matches(haystack: str, keywords: Iterable[str]) -> bool:
    from .cme_evidence_quality import _matches as _eq_matches

    return _eq_matches(haystack, keywords)


def frame_is_relevant_evidence(
    fa: Any,
    claim_id: str,
    claim_text: str,
    *,
    physical_exam: Optional[bool] = None,
    rom_claim: Optional[bool] = None,
) -> bool:
    """Return False for B-roll / ambient frames that should not cite a physical-exam claim."""
    return frame_passes_quality_gates(
        fa, claim_id, claim_text, physical_exam=physical_exam, rom_claim=rom_claim
    )


def relevant_frames(
    claim_id: str,
    claim_text: str,
    frame_analyses: List[Any],
    *,
    max_frames: int = 20,
) -> List[Any]:
    """Frames matching claim keywords that pass centralized quality gates."""
    matched = filter_frames_for_claim(frame_analyses, claim_id, claim_text)
    return select_evidence_frames_for_claim(
        matched, claim_id, claim_text, max_frames=max_frames
    )


def relevant_observations(
    claim_id: str,
    claim_text: str,
    observations: List[Any],
    *,
    max_items: int = 15,
    text_field: str = "text",
    notes_field: str = "notes",
) -> List[Any]:
    """Match transcript / behavior observations by keyword. Supports dicts
    or dataclass instances (duck typed)."""

    keywords = _expand_claim_keywords(claim_id, claim_text)
    if not keywords:
        return []

    def obs_field(o: Any, name: str, default: str = "") -> str:
        if isinstance(o, dict):
            return str(o.get(name, default) or default)
        return str(getattr(o, name, default) or default)

    out: List[Any] = []
    for o in observations or []:
        if _matches(obs_field(o, text_field), keywords):
            out.append(o)
            continue
        if _matches(obs_field(o, notes_field), keywords):
            out.append(o)
            continue
        if _matches(obs_field(o, "explanation"), keywords):
            out.append(o)
            continue
        if _matches(obs_field(o, "problematic_quote"), keywords):
            out.append(o)
    return out[:max_items]


def _fmt_observation_line(o: Any) -> str:
    g = (
        (lambda k, d="": o.get(k, d) if isinstance(o, dict) else getattr(o, k, d))
    )
    speaker = str(g("speaker", "") or "unknown")
    ts = float(g("start_sec", 0.0) or 0.0)
    text = str(g("text", "") or "")
    quote = str(g("problematic_quote", "") or "")
    explanation = str(g("explanation", "") or "")
    notes = str(g("notes", "") or "")
    body = quote or text or explanation or notes
    return f"[{speaker} @ {ts:.1f}s] {body[:220]}"


def _build_summaries(
    claim_id: str,
    claim_text: str,
    frame_analyses: List[Any],
    behavior_observations: List[Any],
    verbal_observations: List[Any],
    *,
    char_budget: int = 4000,
):
    """Return (visual_summary, verbal_summary, counts) within the char budget."""

    frames = relevant_frames(claim_id, claim_text, frame_analyses)
    behavior = relevant_observations(
        claim_id, claim_text, behavior_observations, text_field="notes"
    )
    verbal = relevant_observations(claim_id, claim_text, verbal_observations)

    visual_summary = summarize_video_evidence(frames)
    verbal_lines: List[str] = [_fmt_observation_line(v) for v in verbal]
    behavior_lines: List[str] = [_fmt_observation_line(b) for b in behavior]

    combined_verbal_lines = verbal_lines + behavior_lines
    if not combined_verbal_lines:
        verbal_summary = "(no transcript or behavior observations matched this claim's keywords)"
    else:
        verbal_summary = "\n".join(combined_verbal_lines)

    if len(visual_summary) > char_budget:
        visual_summary = visual_summary[: char_budget - 20] + "\n... [truncated]"
    if len(verbal_summary) > char_budget:
        verbal_summary = verbal_summary[: char_budget - 20] + "\n... [truncated]"

    counts = {
        "matched_frame_count": len(frames),
        "matched_behavior_count": len(behavior),
        "matched_verbal_count": len(verbal),
    }
    return visual_summary, verbal_summary, counts


def _coerce_claim_text(claim_payload: Any) -> str:
    if claim_payload is None:
        return ""
    if isinstance(claim_payload, str):
        return claim_payload
    try:
        return json.dumps(claim_payload, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(claim_payload)


def _strip_fences(text: str) -> str:
    t = text or ""
    if "```json" in t:
        try:
            return t.split("```json", 1)[1].split("```", 1)[0]
        except IndexError:
            return t
    if "```" in t:
        try:
            return t.split("```", 1)[1].split("```", 1)[0]
        except IndexError:
            return t
    return t


_VALID_VERDICTS = {
    "supported",
    "partially_supported",
    "contradicted",
    "not_shown",
    "insufficient_evidence",
}


def _parse_verdict_payload(raw: str) -> Optional[Dict[str, Any]]:
    body = _strip_fences(raw).strip()
    if not body:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if (data.get("verdict") or "").strip().lower() not in _VALID_VERDICTS:
        return None
    return data


def _evidence_from_payload(
    items: Any,
    *,
    frame_raw_lookup: Dict[str, str],
) -> List[Evidence]:
    out: List[Evidence] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        kind = str(it.get("kind", "") or "frame").strip().lower()
        if kind not in {"frame", "frame_range", "quote", "transcript_span", "absence"}:
            kind = "frame"
        frame_id = it.get("frame_id")
        if frame_id is not None:
            frame_id = str(frame_id)
        raw_ref = frame_raw_lookup.get(frame_id) if frame_id else None
        try:
            ts = it.get("timestamp_sec")
            ts = float(ts) if ts is not None else None
        except (TypeError, ValueError):
            ts = None
        try:
            ets = it.get("end_timestamp_sec")
            ets = float(ets) if ets is not None else None
        except (TypeError, ValueError):
            ets = None
        out.append(
            Evidence(
                kind=kind,
                frame_id=frame_id,
                timestamp_sec=ts,
                end_timestamp_sec=ets,
                quote=(str(it["quote"]) if it.get("quote") is not None else None),
                speaker=(str(it["speaker"]) if it.get("speaker") is not None else None),
                raw_response_ref=raw_ref,
                notes=str(it.get("notes", "") or ""),
            )
        )
    return out


def _frame_lookup_by_id(frame_analyses: List[Any]) -> Dict[str, Any]:
    """Map frame_id -> frame analysis dict/object."""
    out: Dict[str, Any] = {}
    for fa in frame_analyses or []:
        if isinstance(fa, dict):
            fid = fa.get("frame_id")
        else:
            fid = getattr(fa, "frame_id", None)
        if fid:
            out[str(fid)] = fa
    return out


def sanitize_claim_evidence(
    evidence: List[Evidence],
    *,
    claim_id: str,
    claim_text: str,
    frame_analyses: List[Any],
) -> List[Evidence]:
    """Drop B-roll / ambient frames from LLM-returned evidence before JSON export."""
    lookup = _frame_lookup_by_id(frame_analyses)
    kept: List[Evidence] = []
    for ev in evidence or []:
        kind = (ev.kind or "").strip().lower()
        if kind == "absence":
            if evidence_notes_are_usable(ev.notes or "", claim_id):
                kept.append(ev)
            continue
        if kind in ("quote", "transcript_span"):
            text = ev.quote or ev.notes or ""
            if evidence_notes_are_usable(text, claim_id):
                kept.append(ev)
            continue
        if kind not in {"frame", "frame_range"}:
            kept.append(ev)
            continue

        fa = lookup.get(str(ev.frame_id or "")) if ev.frame_id else None
        if fa is not None and not frame_passes_quality_gates(fa, claim_id, claim_text):
            continue

        notes = (ev.notes or "").strip()
        if fa is not None:
            if not evidence_notes_are_usable(notes, claim_id, frame=fa):
                desc = evidence_description_for_frame(fa, claim_id)
                if not desc:
                    continue
                ev = Evidence(
                    kind=ev.kind,
                    frame_id=ev.frame_id,
                    timestamp_sec=ev.timestamp_sec,
                    end_timestamp_sec=ev.end_timestamp_sec,
                    quote=ev.quote,
                    speaker=ev.speaker,
                    raw_response_ref=ev.raw_response_ref,
                    notes=desc,
                )
        elif notes and not evidence_notes_are_usable(notes, claim_id):
            continue
        kept.append(ev)
    return kept


def _frame_raw_lookup(frame_analyses: List[Any]) -> Dict[str, str]:
    """Map frame_id -> raw_response path (or empty inline string) so the
    verifier can populate Evidence.raw_response_ref pointers."""
    out: Dict[str, str] = {}
    for fa in frame_analyses or []:
        if isinstance(fa, dict):
            fid = fa.get("frame_id")
            ref = fa.get("raw_response")
        else:
            fid = getattr(fa, "frame_id", None)
            ref = getattr(fa, "raw_response", None)
        if fid and isinstance(ref, str) and ref.strip():
            out[str(fid)] = ref
    return out


def verify_claim(
    claim_id: str,
    claim_payload: Any,
    *,
    frame_analyses: List[Any],
    behavior_observations: List[Any],
    verbal_observations: List[Any],
    vision_client: Any,
    model_id: Optional[str] = None,
    output_dir: Optional[Path] = None,
    research_context: str = "",
) -> ClaimVerdict:
    """Verify ONE claim. Provider-agnostic: only uses the client's
    `text_analyze`. On parse failure, returns an `insufficient_evidence`
    verdict and the raw text is persisted under `claim_verdicts_raw/`
    for the provenance bundle."""

    claim_text = _coerce_claim_text(claim_payload)
    visual_summary, verbal_summary, counts = _build_summaries(
        claim_id,
        claim_text,
        frame_analyses,
        behavior_observations,
        verbal_observations,
    )

    total_frames = len(frame_analyses or [])
    research_section = ""
    if (research_context or "").strip():
        research_section = (
            "\nEXTERNAL RESEARCH CONTEXT (supplemental standards only; video/transcript "
            "evidence always takes precedence — do not treat this as proof the test occurred)\n"
            f"{research_context.strip()[:1200]}\n"
        )
    prompt = CLAIM_VERIFIER_PROMPT.format(
        claim_id=claim_id,
        claim_text=claim_text[:600],
        visual_summary=visual_summary,
        verbal_summary=verbal_summary,
        total_frames=total_frames,
        matched_frame_count=counts["matched_frame_count"],
        matched_behavior_count=counts["matched_behavior_count"],
        matched_verbal_count=counts["matched_verbal_count"],
        research_section=research_section,
    )

    provider = getattr(vision_client, "provider", "")
    default_model_id = getattr(vision_client, "default_model_id", "") or ""

    try:
        result = vision_client.text_analyze(
            prompt, model_id=model_id, max_tokens=1500
        )
        raw_text = getattr(result, "text", "") or ""
        used_model = getattr(result, "model_id", "") or model_id or default_model_id
        used_provider = getattr(result, "provider", "") or provider
    except Exception as e:
        raw_text = f"[verifier exception] {type(e).__name__}: {e}"
        used_model = model_id or default_model_id
        used_provider = provider

    if output_dir is not None:
        try:
            raw_dir = Path(output_dir) / "claim_verdicts_raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / f"{claim_id}.txt").write_text(raw_text, encoding="utf-8")
        except OSError:
            pass

    parsed = _parse_verdict_payload(raw_text)
    if parsed is None:
        return ClaimVerdict(
            claim_id=claim_id,
            claim_text=claim_text,
            claim_payload=claim_payload,
            verdict="insufficient_evidence",
            confidence=0.0,
            reasoning="model output unparseable",
            evidence=[],
            model_id=used_model,
            provider=used_provider,
            prompt_version=CLAIM_VERIFIER_PROMPT_VERSION,
        )

    try:
        conf = float(parsed.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))

    raw_lookup = _frame_raw_lookup(frame_analyses)
    evidence = _evidence_from_payload(parsed.get("evidence"), frame_raw_lookup=raw_lookup)
    evidence = sanitize_claim_evidence(
        evidence,
        claim_id=claim_id,
        claim_text=claim_text,
        frame_analyses=frame_analyses,
    )

    return ClaimVerdict(
        claim_id=claim_id,
        claim_text=claim_text,
        claim_payload=claim_payload,
        verdict=str(parsed.get("verdict") or "insufficient_evidence").strip().lower(),
        confidence=conf,
        reasoning=str(parsed.get("reasoning") or "").strip(),
        evidence=evidence,
        model_id=used_model,
        provider=used_provider,
        prompt_version=CLAIM_VERIFIER_PROMPT_VERSION,
    )


def _load_claim_checkpoint(path: Path) -> Dict[str, dict]:
    """Load NDJSON per-claim checkpoint rows keyed by claim_id. Returns an
    empty dict when the file is missing or unreadable."""
    done: Dict[str, dict] = {}
    if not path or not path.exists():
        return done
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return done
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        cid = row.get("claim_id")
        if not cid:
            continue
        # NDJSON: keep the latest row per claim_id (replay-friendly).
        done[str(cid)] = row.get("verdict_record") or row
    return done


def _claim_checkpoint_has_real_verdict(row: dict) -> bool:
    """A checkpoint row counts as "done" only when its verdict is one of
    the four substantive labels; `insufficient_evidence` is treated as a
    failure-stub (often from an unparseable model response) and is
    retried on resume. Mirrors the per-frame behavior-pass pattern."""
    if not isinstance(row, dict):
        return False
    verdict = str(row.get("verdict") or "").strip().lower()
    if not verdict:
        return False
    return verdict in {"supported", "partially_supported", "contradicted", "not_shown"}


def _append_claim_checkpoint(checkpoint_path: Path, lock: Any, verdict: ClaimVerdict) -> None:
    """Persist one verdict to the per-claim NDJSON checkpoint under lock."""
    try:
        payload = {"claim_id": verdict.claim_id, "verdict_record": asdict(verdict)}
        line = json.dumps(payload, default=str, ensure_ascii=False) + "\n"
    except (TypeError, ValueError):
        return
    with lock:
        try:
            with open(checkpoint_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass


def verify_all_claims(
    claims: Dict[str, Any],
    *,
    frame_analyses: List[Any],
    behavior_observations: List[Any],
    verbal_observations: List[Any],
    vision_client: Any,
    output_dir: Path,
    max_workers: int = 4,
    model_id: Optional[str] = None,
    resume: bool = False,
    research_client: Any = None,
) -> List[ClaimVerdict]:
    """Verify every claim in `claims`. Persists `claim_verdicts.json` to
    `output_dir / "claim_verdicts.json"`. Returns the list, sorted by
    claim_id for stable diffs across runs.

    When `resume=True`, reuses any prior per-claim verdicts recorded in
    `output_dir / "claim_verdicts_checkpoint.jsonl"` whose verdict is one
    of the four substantive labels (`supported`, `partially_supported`,
    `contradicted`, `not_shown`). Rows whose previous verdict was
    `insufficient_evidence` (the failure stub produced by an unparseable
    model response) are retried. Default behavior is unchanged
    (`resume=False` truncates the checkpoint up-front)."""

    import threading

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    claims = filter_medical_claims(claims)
    items = list((claims or {}).items())
    if not items:
        path = output_dir / "claim_verdicts.json"
        path.write_text(json.dumps([], indent=2), encoding="utf-8")
        return []

    checkpoint_path = output_dir / "claim_verdicts_checkpoint.jsonl"
    resumed: Dict[str, dict] = {}
    if resume and checkpoint_path.exists():
        resumed = _load_claim_checkpoint(checkpoint_path)
    elif checkpoint_path.exists():
        try:
            checkpoint_path.unlink()
        except OSError:
            pass

    workers = max(1, int(max_workers or 1))
    verdicts: List[ClaimVerdict] = []
    pending_items: List[tuple] = []
    retried_failed = 0
    for cid, payload in items:
        prior = resumed.get(str(cid))
        if prior and _claim_checkpoint_has_real_verdict(prior):
            try:
                ev_list = [Evidence(**e) for e in (prior.get("evidence") or []) if isinstance(e, dict)]
            except TypeError:
                ev_list = []
            claim_text = str(prior.get("claim_text") or _coerce_claim_text(payload))
            ev_list = sanitize_claim_evidence(
                ev_list,
                claim_id=str(cid),
                claim_text=claim_text,
                frame_analyses=frame_analyses,
            )
            verdicts.append(
                ClaimVerdict(
                    claim_id=str(prior.get("claim_id") or cid),
                    claim_text=claim_text,
                    claim_payload=prior.get("claim_payload"),
                    verdict=str(prior.get("verdict") or "insufficient_evidence"),
                    confidence=float(prior.get("confidence") or 0.0),
                    reasoning=str(prior.get("reasoning") or ""),
                    evidence=ev_list,
                    model_id=str(prior.get("model_id") or ""),
                    provider=str(prior.get("provider") or ""),
                    prompt_version=str(
                        prior.get("prompt_version") or CLAIM_VERIFIER_PROMPT_VERSION
                    ),
                )
            )
        else:
            pending_items.append((cid, payload))
            if prior:
                retried_failed += 1

    if resume:
        print(
            f"Claim verifier resume: {len(items)} total, "
            f"{len(verdicts)} from checkpoint, {len(pending_items)} pending, "
            f"{retried_failed} retrying failed stubs."
        )

    ckpt_lock = threading.Lock()
    research_cache_path = output_dir / "research_cache.json"
    research_cache: Dict[str, dict] = {}
    if research_client is not None and getattr(research_client, "enabled", False):
        from .perplexity_client import (
            format_research_context,
            load_research_cache,
            save_research_cache,
        )

        research_cache = load_research_cache(str(research_cache_path))
        print(
            f"Perplexity research enabled for claim verification "
            f"({len(research_cache)} cached entries)."
        )

    def _research_context_for(cid_local: str, payload_local: Any) -> str:
        claim_text = _coerce_claim_text(payload_local)
        hunter_ctx = hunter_methodology_context_for_claim(str(cid_local), claim_text)
        external_ctx = ""
        if research_client is not None and getattr(research_client, "enabled", False):
            from .perplexity_client import ResearchResult, format_research_context

            cached = research_cache.get(str(cid_local))
            if isinstance(cached, dict) and cached.get("summary"):
                result = ResearchResult(
                    claim_id=str(cached.get("claim_id") or cid_local),
                    query=str(cached.get("query") or ""),
                    summary=str(cached.get("summary") or ""),
                    citations=list(cached.get("citations") or []),
                    model_id=str(cached.get("model_id") or ""),
                    latency_ms=int(cached.get("latency_ms") or 0),
                    error=str(cached.get("error") or ""),
                )
                external_ctx = format_research_context(result)
            else:
                result = research_client.research_for_claim(str(cid_local), claim_text)
                research_cache[str(cid_local)] = {
                    "claim_id": result.claim_id,
                    "query": result.query,
                    "summary": result.summary,
                    "citations": result.citations,
                    "model_id": result.model_id,
                    "latency_ms": result.latency_ms,
                    "error": result.error,
                }
                save_research_cache(str(research_cache_path), research_cache)
                external_ctx = format_research_context(result)
        if hunter_ctx and external_ctx:
            return f"{hunter_ctx}\n\n{external_ctx}"
        return hunter_ctx or external_ctx

    def _run_one(cid_local, payload_local) -> ClaimVerdict:
        v = verify_claim(
            cid_local,
            payload_local,
            frame_analyses=frame_analyses,
            behavior_observations=behavior_observations,
            verbal_observations=verbal_observations,
            vision_client=vision_client,
            model_id=model_id,
            output_dir=output_dir,
            research_context=_research_context_for(cid_local, payload_local),
        )
        _append_claim_checkpoint(checkpoint_path, ckpt_lock, v)
        return v

    if pending_items:
        if workers == 1 or len(pending_items) == 1:
            for cid, payload in pending_items:
                verdicts.append(_run_one(cid, payload))
        else:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                future_map = {
                    ex.submit(_run_one, cid, payload): cid for cid, payload in pending_items
                }
                for fut in as_completed(future_map):
                    verdicts.append(fut.result())

    verdicts.sort(key=lambda v: v.claim_id)

    verdicts = [v for v in verdicts if not is_metadata_claim_id(v.claim_id)]

    payload = [asdict(v) for v in verdicts]
    path = output_dir / "claim_verdicts.json"
    path.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    return verdicts
