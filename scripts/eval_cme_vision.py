#!/usr/bin/env python3
"""
Real eval harness for the CME vision analyzers.

This script grades the production analyzers
(`CMEComprehensiveAnalyzer.analyze_frame` and
`CMEBehaviorAnalyzer.analyze_frame_behavior`) against the human-curated
golden set in `tests/fixtures/golden_set/`. It does NOT score the analyzer
against its own historical outputs; the gold labels in
`tests/fixtures/golden_set/manifest.json` were derived independently and
are the source of truth for this run. See `docs/golden_set_curation.md`
for the curation rationale and `docs/eval_runbook.md` for the operator
playbook.

CLI summary (run `--help` for the canonical list):
    --manifest                Path to the golden-set manifest JSON.
    --providers               Comma-separated vendor list. The first entry
                              is the "primary" provider (the one that drives
                              pass/fail). Default: anthropic.
    --output-dir              Directory to land per-frame outputs in.
                              Default: eval_runs/<timestamp>/.
    --max-workers             ThreadPool size for vision calls.
    --passes                  comprehensive | behavior | claims | all.
    --compare-to              Optional eval_summary.json from a prior run;
                              if set, the eval is also graded as a delta.
    --threshold-pass-rate     Absolute pass-rate floor. Eval exits non-zero
                              when the overall rate is below this.
    --threshold-regression    Max allowed regression vs --compare-to baseline.
    --json-out / --markdown-out  Override the default output paths.
    --dry-run                 Print the planned set of (clip, frame, pass)
                              tuples and exit 0; no API calls are made.
    --resume                  Skip per-frame outputs that already exist on
                              disk under <output-dir>/raw/<pass>/<clip>/.

Scoring rules:
    - Categorical fields (test_type, body_region, patient_attire, visibility):
      exact match, case-insensitive.
    - Boolean fields (doctor_facing_patient, doctor_making_eye_contact,
      doctor_on_phone_or_distracted, patient_visible_distress, ...): exact
      match.
    - The `notes` field is a free-text comparison. We extract 3-6 noun-ish
      phrases from the gold note via a light heuristic (split on punctuation,
      drop stopwords, keep tokens of length >= 4) and the field passes if at
      least 50% of those phrases appear in the model's output `notes`. This
      is intentionally lenient because the gold notes are full sentences
      while the model output is too. Reviewers can tune the 50% threshold.
    - `confidence` passes when the reported number is >= 0.5 AND
      `visibility` matches the gold label. This catches the failure mode
      where the model is overconfident on an obscured frame.
    - Only fields present in `expected` are compared. Missing labels are
      intentional (see the curation doc) and never penalized.

Aggregation and exit codes:
    pass_rate = fields_passed / fields_evaluated across every (clip, frame,
    pass, field) tuple. The eval exits 1 when:
      - manifest validation fails, OR
      - --compare-to was set but the baseline file does not exist, OR
      - the absolute pass_rate falls below --threshold-pass-rate, OR
      - --compare-to is set AND the pass_rate regressed by more than
        --threshold-regression vs the baseline.
    Otherwise it exits 0. The verdict, reasons, per-clip rollup, per-field
    rollup, top failures, and (when --compare-to is set) the delta block
    are all in `eval_summary.json` and `eval_summary.md`.

Defaults are tuned for local, Anthropic-only runs:
    ANTHROPIC_API_KEY=... python scripts/eval_cme_vision.py

is the recommended invocation; no other flags are required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Imports from the backend package. These are import-time light (no API key
# required) because the analyzers only construct a real client when
# instantiated. Tests rely on this property.
from backend.lambda_functions.cme_analysis_utils import DEFAULT_SONNET_MODEL  # noqa: E402
from backend.lambda_functions.cme_behavior_analyzer import (  # noqa: E402
    CMEBehaviorAnalyzer,
    VisualBehaviorObservation,
)
from backend.lambda_functions.cme_claim_verifier import (  # noqa: E402
    CLAIM_VERIFIER_PROMPT_VERSION,
)
from backend.lambda_functions.cme_comprehensive_analyzer import (  # noqa: E402
    CMEComprehensiveAnalyzer,
    FrameAnalysis,
)
from backend.lambda_functions.prompts.production import (  # noqa: E402
    BEHAVIOR_VISUAL_PROMPT_VERSION,
    TECHNIQUE_FRAME_PROMPT_VERSION,
)
from backend.lambda_functions.vision_client import (  # noqa: E402
    PROVIDER_PRICING,
    VisionClient,
    VisionClientConfigError,
    default_model_for,
    make_vision_client,
)


# ----------------------------------------------------------------------
# Constants / scoring config
# ----------------------------------------------------------------------

MANIFEST_DEFAULT = REPO_ROOT / "tests/fixtures/golden_set/manifest.json"
SCHEMA_DEFAULT = REPO_ROOT / "tests/fixtures/golden_set/schema/manifest.schema.json"

CATEGORICAL_FIELDS = {"test_type", "body_region", "patient_attire", "visibility"}
BOOLEAN_FIELDS = {
    "doctor_facing_patient",
    "doctor_making_eye_contact",
    "doctor_on_phone_or_distracted",
    "patient_visible_distress",
    "patient_trying_to_speak",
    "doctor_appears_rushed",
    "doctor_dismissive_gesture",
}

# Behavior pass exposes the same booleans plus a few extras (looking at
# phone, leaning_in, etc.). Comparing field-name to field-name across the
# two analyzers is intentional; the analyzers share vocabulary.
BEHAVIOR_BOOLEAN_FIELDS = {
    "doctor_looking_at_patient",
    "doctor_looking_at_phone",
    "doctor_looking_at_notes",
    "doctor_facing_patient",
    "doctor_turned_away",
    "patient_appears_distressed",
    "patient_trying_to_speak",
    "appears_rushed",
    "dismissive_gesture",
}

NOTES_FIELD = "notes"
CONFIDENCE_FIELD = "confidence"

# Hard-coded short stopword set used by the noun-phrase heuristic. Keep this
# inline rather than depending on nltk; the eval is supposed to run in a
# vanilla CI image. Common gerunds / action verbs that show up in nearly
# every CME description (wearing, looking, writing, ...) are excluded so
# the heuristic focuses on content-bearing nouns. Reviewers can extend
# this list; tests/test_eval_script.py covers the canonical examples.
_STOPWORDS = frozenset(
    """
    a an and the of in on at to for from with into onto by is are was were be been being
    has have had do does did this that these those it its their there here as if
    but or so not no yes very also too just then than which who whom whose what when where why how
    over under between among through during before after about against around without within
    while up down out off again further still each any all some many few more most less other
    such only own same own
    wearing looking writing reading walking sitting standing seated standing
    facing turned holding watching saying telling making taking giving showing
    """.split()
)

ALL_PASSES = ("comprehensive", "behavior", "claims")


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------


@dataclass
class FieldResult:
    field_name: str
    expected: Any
    actual: Any
    passed: bool
    reason: str


@dataclass
class FrameResult:
    clip_id: str
    pass_name: str  # "comprehensive" | "behavior"
    frame_filename: str
    provider: str
    model_id: str
    fields: Dict[str, FieldResult] = field(default_factory=dict)
    frame_pass_rate: float = 0.0
    raw_response_excerpt: str = ""
    error: Optional[str] = None
    usd_cost_estimate: Optional[float] = None


@dataclass
class ClipPlan:
    clip_id: str
    frames_dir: Path
    expected: Dict[str, Any]
    frame_paths: List[Path]


# ----------------------------------------------------------------------
# Manifest validation
# ----------------------------------------------------------------------


def _basic_manifest_check(data: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("manifest root must be an object")
    if int(data.get("schema_version", 0)) < 1:
        raise ValueError("manifest.schema_version must be >= 1")
    clips = data.get("clips")
    if not isinstance(clips, list) or not clips:
        raise ValueError("manifest.clips must be a non-empty list")
    seen_ids: set = set()
    for c in clips:
        if not isinstance(c, dict):
            raise ValueError("each clip entry must be an object")
        for required in ("id", "frames_dir", "eval_frame_glob", "expected"):
            if required not in c:
                raise ValueError(f"clip missing required field {required!r}: {c}")
        cid = c["id"]
        if cid in seen_ids:
            raise ValueError(f"duplicate clip id {cid!r}")
        seen_ids.add(cid)
        if not isinstance(c["expected"], dict):
            raise ValueError(f"clip {cid!r}: expected must be an object")


def validate_manifest(
    manifest_path: Path,
    schema_path: Path = SCHEMA_DEFAULT,
) -> Dict[str, Any]:
    """Load + validate the manifest. Uses jsonschema if importable; falls
    back to a minimal structural check otherwise so the eval still runs
    in stripped-down environments. Fails fast on error."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    try:
        import jsonschema  # type: ignore

        if schema_path.exists():
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(instance=data, schema=schema)
    except ImportError:
        # Fall back to the structural check; surfaced via print so the run
        # is auditable.
        print(
            "[warn] jsonschema not installed; falling back to structural manifest check",
            file=sys.stderr,
        )

    _basic_manifest_check(data)
    return data


def schema_supports_claims(schema_path: Path = SCHEMA_DEFAULT) -> bool:
    """Returns True when the golden-set schema declares a `claims` (or
    `expected_claim_verdicts`) sub-block. The current schema does NOT, so
    the claims pass cleanly no-ops; this helper exists so when the schema
    is upgraded we automatically light up the pass."""
    if not schema_path.exists():
        return False
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    clip_props = (
        schema.get("properties", {})
        .get("clips", {})
        .get("items", {})
        .get("properties", {})
    )
    return any(k in clip_props for k in ("claims", "expected_claim_verdicts"))


# ----------------------------------------------------------------------
# Scoring helpers (pure functions; tested directly)
# ----------------------------------------------------------------------


def _norm(s: Any) -> str:
    return (str(s) if s is not None else "").strip().lower()


def compare_categorical(expected: Any, actual: Any) -> Tuple[bool, str]:
    """Exact, case-insensitive equality for canonical taxonomy fields."""
    e, a = _norm(expected), _norm(actual)
    return e == a, f"expected={expected!r} actual={actual!r}"


def compare_boolean(expected: Any, actual: Any) -> Tuple[bool, str]:
    """Strict equality after coercing both sides to bool."""
    try:
        e = bool(expected)
        a = bool(actual)
    except Exception:
        return False, f"could not coerce to bool: expected={expected!r} actual={actual!r}"
    return e == a, f"expected={e} actual={a}"


def extract_phrases(text: str, *, min_len: int = 4, max_phrases: int = 6) -> List[str]:
    """Pull 3-6 noun-ish phrases out of the gold `notes` field.

    Implementation: split on punctuation and whitespace, drop stopwords,
    keep tokens of length >= min_len. This is heuristic by design; the
    docstring at the top of this file calls out that reviewers will tune
    it. Tested with synthetic inputs in tests/test_eval_script.py."""
    if not text:
        return []
    norm = text.lower()
    tokens = re.split(r"[^a-z0-9]+", norm)
    phrases: List[str] = []
    seen: set = set()
    for tok in tokens:
        if len(tok) < min_len:
            continue
        if tok in _STOPWORDS:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        phrases.append(tok)
        if len(phrases) >= max_phrases:
            break
    return phrases


def compare_notes(
    expected: Any,
    actual: Any,
    *,
    threshold: float = 0.5,
) -> Tuple[bool, str]:
    """Pass if at least `threshold` fraction of the gold note's noun
    phrases appear (case-insensitive substring) in the model's notes
    output. See `extract_phrases` for the noun-phrase rule."""
    gold = str(expected or "")
    cand = _norm(actual)
    phrases = extract_phrases(gold)
    if not phrases:
        # No discriminating phrases; treat as informational pass to avoid
        # punishing a clip whose gold note is too short to compare.
        return True, "expected note has no scoreable phrases"
    hits = [p for p in phrases if p in cand]
    rate = len(hits) / len(phrases)
    ok = rate >= threshold
    return ok, (
        f"matched {len(hits)}/{len(phrases)} phrases ({rate:.0%}); "
        f"phrases={phrases} hits={hits}"
    )


def compare_confidence(
    expected_visibility: Any,
    actual_visibility: Any,
    actual_confidence: Any,
    *,
    floor: float = 0.5,
) -> Tuple[bool, str]:
    """Pass when confidence >= floor AND visibility matches.

    Designed to catch overconfidence on obscured / partial frames: a model
    that reports confidence=0.9 on a frame the gold set labels obscured
    should NOT get credit for the confidence field even though the number
    is high in isolation."""
    try:
        conf = float(actual_confidence)
    except (TypeError, ValueError):
        return False, f"confidence not numeric: {actual_confidence!r}"
    vis_match = _norm(expected_visibility) == _norm(actual_visibility)
    if not vis_match:
        return False, (
            f"confidence={conf:.2f} but visibility mismatch "
            f"(expected={expected_visibility!r} actual={actual_visibility!r})"
        )
    if conf < floor:
        return False, f"confidence={conf:.2f} below floor {floor:.2f}"
    return True, f"confidence={conf:.2f} >= {floor:.2f} and visibility matches"


def _booleanish(field_name: str, pass_name: str) -> bool:
    if pass_name == "comprehensive":
        return field_name in BOOLEAN_FIELDS
    if pass_name == "behavior":
        return field_name in BEHAVIOR_BOOLEAN_FIELDS
    return False


def _categoricalish(field_name: str) -> bool:
    return field_name in CATEGORICAL_FIELDS


def score_frame(
    *,
    expected: Dict[str, Any],
    actual: Dict[str, Any],
    pass_name: str,
) -> Tuple[Dict[str, FieldResult], float]:
    """Compare `actual` against `expected` per the rules at the top of this
    file. Only fields present in `expected` are considered. Returns the
    per-field result map plus the frame-level pass rate."""
    field_results: Dict[str, FieldResult] = {}
    if not expected:
        return field_results, 1.0  # nothing to score, treat as neutral pass

    for key, gold in expected.items():
        if key == NOTES_FIELD:
            ok, reason = compare_notes(gold, actual.get(NOTES_FIELD))
            field_results[key] = FieldResult(
                field_name=key,
                expected=gold,
                actual=actual.get(NOTES_FIELD, ""),
                passed=ok,
                reason=reason,
            )
            continue
        if key == CONFIDENCE_FIELD:
            ok, reason = compare_confidence(
                expected.get("visibility"),
                actual.get("visibility"),
                actual.get(CONFIDENCE_FIELD),
            )
            field_results[key] = FieldResult(
                field_name=key,
                expected=gold,
                actual=actual.get(CONFIDENCE_FIELD),
                passed=ok,
                reason=reason,
            )
            continue
        if _categoricalish(key):
            ok, reason = compare_categorical(gold, actual.get(key, ""))
            field_results[key] = FieldResult(
                field_name=key, expected=gold, actual=actual.get(key, ""),
                passed=ok, reason=reason,
            )
            continue
        if _booleanish(key, pass_name):
            ok, reason = compare_boolean(gold, actual.get(key))
            field_results[key] = FieldResult(
                field_name=key, expected=gold, actual=actual.get(key),
                passed=ok, reason=reason,
            )
            continue
        # Unrecognized field for this pass. Some gold blocks include
        # technique_issues / equipment_visible (list-valued); list-valued
        # fields are scored as subset match (every gold token must appear
        # in actual). This keeps the eval honest without inventing a new
        # taxonomy.
        if isinstance(gold, list):
            actual_list = actual.get(key, []) or []
            gold_set = {str(x).strip().lower() for x in gold if x}
            actual_set = {str(x).strip().lower() for x in actual_list if x}
            missing = sorted(gold_set - actual_set)
            ok = not missing
            field_results[key] = FieldResult(
                field_name=key, expected=gold, actual=actual_list,
                passed=ok,
                reason=(f"missing={missing}" if missing else "all gold tokens present"),
            )
            continue
        # Unknown scalar - fall back to case-insensitive exact match.
        ok, reason = compare_categorical(gold, actual.get(key, ""))
        field_results[key] = FieldResult(
            field_name=key, expected=gold, actual=actual.get(key, ""),
            passed=ok, reason=reason,
        )

    passed = sum(1 for r in field_results.values() if r.passed)
    total = len(field_results)
    rate = passed / total if total else 1.0
    return field_results, rate


# ----------------------------------------------------------------------
# Plan + execution
# ----------------------------------------------------------------------


def build_plan(manifest: Dict[str, Any], manifest_path: Path) -> List[ClipPlan]:
    """Resolve each clip's frames on disk. Skips clips whose frames_dir is
    missing (with a printed warning) so a partial bootstrap still runs."""
    base = manifest_path.parent
    plans: List[ClipPlan] = []
    for clip in manifest.get("clips", []):
        cid = clip["id"]
        frames_dir = (base / clip["frames_dir"]).resolve()
        if not frames_dir.is_dir():
            print(f"[skip] clip {cid!r}: frames_dir missing -> {frames_dir}", file=sys.stderr)
            continue
        frame_paths = sorted(frames_dir.glob("*.jpg"))
        if not frame_paths:
            print(f"[skip] clip {cid!r}: no .jpg frames under {frames_dir}", file=sys.stderr)
            continue
        plans.append(
            ClipPlan(
                clip_id=cid,
                frames_dir=frames_dir,
                expected=dict(clip.get("expected") or {}),
                frame_paths=frame_paths,
            )
        )
    return plans


def _frame_output_path(output_dir: Path, pass_name: str, clip_id: str, frame: Path) -> Path:
    return output_dir / "raw" / pass_name / clip_id / f"{frame.stem}.json"


def _excerpt(text: str, limit: int = 400) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _frame_analysis_to_dict(fa: FrameAnalysis) -> Dict[str, Any]:
    return asdict(fa)


def _behavior_obs_to_dict(obs: VisualBehaviorObservation) -> Dict[str, Any]:
    return asdict(obs)


def _run_comprehensive_pass(
    plans: List[ClipPlan],
    *,
    analyzer: CMEComprehensiveAnalyzer,
    output_dir: Path,
    max_workers: int,
    resume: bool,
) -> List[FrameResult]:
    """Run the comprehensive pass against every (clip, frame) and grade it."""
    tasks: List[Tuple[ClipPlan, Path]] = []
    for plan in plans:
        for fp in plan.frame_paths:
            tasks.append((plan, fp))

    results: List[FrameResult] = []
    if not tasks:
        return results

    def _one(plan: ClipPlan, frame_path: Path) -> FrameResult:
        out_path = _frame_output_path(output_dir, "comprehensive", plan.clip_id, frame_path)
        actual: Dict[str, Any] = {}
        excerpt = ""
        cost: Optional[float] = None
        err: Optional[str] = None
        provider = getattr(analyzer.vision_client, "provider", "")
        model_id = getattr(analyzer.vision_client, "default_model_id", "") or ""

        try:
            if resume and out_path.exists():
                actual = json.loads(out_path.read_text(encoding="utf-8"))
            else:
                analysis = analyzer.analyze_frame(frame_path, interval_sec=1.0)
                actual = _frame_analysis_to_dict(analysis)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(actual, indent=2, default=str), encoding="utf-8"
                )
            excerpt = _excerpt(str(actual.get("raw_response") or ""))
            cost = actual.get("usd_cost_estimate")
            provider = actual.get("provider") or provider
            model_id = actual.get("model_id") or model_id
        except Exception as e:
            err = f"{type(e).__name__}: {e}"

        fields, frame_rate = score_frame(
            expected=plan.expected, actual=actual, pass_name="comprehensive"
        )
        return FrameResult(
            clip_id=plan.clip_id,
            pass_name="comprehensive",
            frame_filename=frame_path.name,
            provider=provider,
            model_id=model_id,
            fields=fields,
            frame_pass_rate=frame_rate,
            raw_response_excerpt=excerpt,
            error=err,
            usd_cost_estimate=cost,
        )

    if max_workers <= 1:
        for plan, fp in tasks:
            results.append(_one(plan, fp))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_one, p, fp) for p, fp in tasks]
            for fut in as_completed(futures):
                results.append(fut.result())
    return results


def _run_behavior_pass(
    plans: List[ClipPlan],
    *,
    analyzer: CMEBehaviorAnalyzer,
    output_dir: Path,
    max_workers: int,
    resume: bool,
) -> List[FrameResult]:
    """Run the behavior pass against every (clip, frame) and grade it
    against any behavior-relevant fields the clip's expected block
    contains. Clips without behavior labels produce zero field-results
    (they don't penalize)."""
    tasks: List[Tuple[ClipPlan, Path]] = []
    for plan in plans:
        for fp in plan.frame_paths:
            tasks.append((plan, fp))

    results: List[FrameResult] = []
    if not tasks:
        return results

    def _one(plan: ClipPlan, frame_path: Path) -> FrameResult:
        out_path = _frame_output_path(output_dir, "behavior", plan.clip_id, frame_path)
        actual: Dict[str, Any] = {}
        excerpt = ""
        cost: Optional[float] = None
        err: Optional[str] = None
        provider = getattr(analyzer.vision_client, "provider", "")
        model_id = getattr(analyzer.vision_client, "default_model_id", "") or ""

        try:
            if resume and out_path.exists():
                actual = json.loads(out_path.read_text(encoding="utf-8"))
            else:
                obs = analyzer.analyze_frame_behavior(frame_path, timestamp_sec=0.0)
                actual = _behavior_obs_to_dict(obs)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(actual, indent=2, default=str), encoding="utf-8"
                )
            excerpt = _excerpt(str(actual.get("raw_response") or ""))
            cost = actual.get("usd_cost_estimate")
            provider = actual.get("provider") or provider
            model_id = actual.get("model_id") or model_id
        except Exception as e:
            err = f"{type(e).__name__}: {e}"

        fields, frame_rate = score_frame(
            expected=plan.expected, actual=actual, pass_name="behavior"
        )
        return FrameResult(
            clip_id=plan.clip_id,
            pass_name="behavior",
            frame_filename=frame_path.name,
            provider=provider,
            model_id=model_id,
            fields=fields,
            frame_pass_rate=frame_rate,
            raw_response_excerpt=excerpt,
            error=err,
            usd_cost_estimate=cost,
        )

    if max_workers <= 1:
        for plan, fp in tasks:
            results.append(_one(plan, fp))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_one, p, fp) for p, fp in tasks]
            for fut in as_completed(futures):
                results.append(fut.result())
    return results


# ----------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------


def aggregate_results(
    *,
    frame_results: List[FrameResult],
    passes_run: List[str],
) -> Dict[str, Any]:
    """Roll frame-level results up into by_clip / by_field / totals.

    Pure function over the FrameResult list so the test suite can exercise
    it with synthetic inputs."""
    by_clip_map: Dict[str, Dict[str, Any]] = {}
    by_field_map: Dict[str, Dict[str, int]] = {}
    total_fields = 0
    total_passed = 0
    estimated_cost = 0.0

    # Stable ordering by clip_id then frame_filename then pass_name keeps
    # the markdown / json output diffable across runs.
    for fr in sorted(
        frame_results,
        key=lambda r: (r.clip_id, r.frame_filename, r.pass_name),
    ):
        clip_bucket = by_clip_map.setdefault(
            fr.clip_id,
            {"clip_id": fr.clip_id, "frames": [], "fields_evaluated": 0, "fields_passed": 0},
        )
        f_passed = sum(1 for f in fr.fields.values() if f.passed)
        f_total = len(fr.fields)
        clip_bucket["fields_evaluated"] += f_total
        clip_bucket["fields_passed"] += f_passed
        clip_bucket["frames"].append(
            {
                "frame_filename": fr.frame_filename,
                "pass": fr.pass_name,
                "fields_evaluated": f_total,
                "fields_passed": f_passed,
                "frame_pass_rate": fr.frame_pass_rate,
                "error": fr.error,
                "provider": fr.provider,
                "model_id": fr.model_id,
                "fields": {k: asdict(v) for k, v in fr.fields.items()},
                "raw_response_excerpt": fr.raw_response_excerpt,
                "usd_cost_estimate": fr.usd_cost_estimate,
            }
        )

        for name, fres in fr.fields.items():
            bucket = by_field_map.setdefault(name, {"evaluated": 0, "passed": 0})
            bucket["evaluated"] += 1
            if fres.passed:
                bucket["passed"] += 1

        total_fields += f_total
        total_passed += f_passed
        if fr.usd_cost_estimate:
            try:
                estimated_cost += float(fr.usd_cost_estimate)
            except (TypeError, ValueError):
                pass

    by_clip = []
    for cid in sorted(by_clip_map):
        bucket = by_clip_map[cid]
        evals = bucket["fields_evaluated"]
        bucket["pass_rate"] = (bucket["fields_passed"] / evals) if evals else 1.0
        by_clip.append(bucket)

    by_field = {}
    for name in sorted(by_field_map):
        bucket = by_field_map[name]
        bucket["pass_rate"] = (
            (bucket["passed"] / bucket["evaluated"]) if bucket["evaluated"] else 1.0
        )
        by_field[name] = bucket

    overall_rate = (total_passed / total_fields) if total_fields else 1.0

    totals = {
        "clips": len(by_clip),
        "frames": len({(fr.clip_id, fr.frame_filename) for fr in frame_results}),
        "passes_run": list(passes_run),
        "fields_evaluated": total_fields,
        "fields_passed": total_passed,
        "pass_rate": overall_rate,
        "estimated_cost_usd": round(estimated_cost, 6),
    }
    return {
        "totals": totals,
        "by_clip": by_clip,
        "by_field": by_field,
    }


# ----------------------------------------------------------------------
# Output writers
# ----------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _format_field_value(v: Any) -> str:
    if isinstance(v, str):
        return v.replace("\n", " ").strip()
    return json.dumps(v, default=str)


def render_markdown(
    summary: Dict[str, Any],
    frame_results: List[FrameResult],
) -> str:
    """Pretty markdown report. The job is to fit on a PR comment, so we
    keep tables short and put long lists in collapsible-ish sections."""
    totals = summary["totals"]
    by_clip = summary["by_clip"]
    by_field = summary["by_field"]
    baseline = summary.get("baseline")
    verdict = summary.get("verdict", "pass")
    reasons = summary.get("verdict_reasons", [])

    lines: List[str] = []
    lines.append(f"# CME Eval Summary - verdict: {verdict.upper()}")
    lines.append("")
    lines.append(
        f"- Pass rate: **{totals['pass_rate']:.1%}** "
        f"({totals['fields_passed']}/{totals['fields_evaluated']} fields)"
    )
    lines.append(f"- Clips: {totals['clips']} | Frames: {totals['frames']}")
    lines.append(f"- Passes run: {', '.join(totals['passes_run'])}")
    lines.append(f"- Primary provider: `{summary.get('primary_provider')}` "
                 f"model: `{summary.get('primary_model_id')}`")
    cost = totals.get("estimated_cost_usd") or 0.0
    lines.append(f"- Estimated cost: ${cost:.4f}")
    if reasons:
        lines.append("")
        lines.append("**Verdict reasons:**")
        for r in reasons:
            lines.append(f"- {r}")

    lines.append("")
    lines.append("## By clip")
    lines.append("")
    lines.append("| clip_id | frames evaluated | fields | pass rate |")
    lines.append("|---|---|---|---|")
    for c in by_clip:
        lines.append(
            f"| {c['clip_id']} | {len(c['frames'])} | "
            f"{c['fields_passed']}/{c['fields_evaluated']} | "
            f"{c['pass_rate']:.1%} |"
        )

    lines.append("")
    lines.append("## By field")
    lines.append("")
    lines.append("| field | evaluated | passed | pass rate |")
    lines.append("|---|---|---|---|")
    for name, b in by_field.items():
        lines.append(
            f"| {name} | {b['evaluated']} | {b['passed']} | {b['pass_rate']:.1%} |"
        )

    # Top 20 failures
    failures: List[Tuple[str, str, str, FieldResult]] = []
    for fr in frame_results:
        for fname, fres in fr.fields.items():
            if not fres.passed:
                failures.append((fr.clip_id, fr.frame_filename, fr.pass_name, fres))
    failures.sort(key=lambda x: (x[0], x[1], x[2], x[3].field_name))
    if failures:
        lines.append("")
        lines.append("## Failures (top 20)")
        lines.append("")
        lines.append("| clip | frame | pass | field | expected | actual | reason |")
        lines.append("|---|---|---|---|---|---|---|")
        for clip_id, frame, pass_name, fres in failures[:20]:
            lines.append(
                f"| {clip_id} | {frame} | {pass_name} | {fres.field_name} | "
                f"`{_format_field_value(fres.expected)[:60]}` | "
                f"`{_format_field_value(fres.actual)[:60]}` | "
                f"{fres.reason[:120]} |"
            )

    if baseline:
        lines.append("")
        lines.append("## Delta vs baseline")
        lines.append("")
        b_totals = baseline.get("totals") or {}
        delta = totals["pass_rate"] - float(b_totals.get("pass_rate", 0.0) or 0.0)
        arrow = "up" if delta > 0 else ("down" if delta < 0 else "flat")
        lines.append(
            f"- Overall pass rate: {totals['pass_rate']:.1%} "
            f"(baseline {b_totals.get('pass_rate', 0.0):.1%}, delta {delta:+.1%} [{arrow}])"
        )
        # Per-field delta when possible
        b_by_field = baseline.get("by_field") or {}
        if b_by_field:
            lines.append("")
            lines.append("| field | this run | baseline | delta |")
            lines.append("|---|---|---|---|")
            for name in sorted(set(list(by_field.keys()) + list(b_by_field.keys()))):
                cur = by_field.get(name, {}).get("pass_rate")
                old = b_by_field.get(name, {}).get("pass_rate")
                cur_s = f"{cur:.1%}" if isinstance(cur, (int, float)) else "-"
                old_s = f"{old:.1%}" if isinstance(old, (int, float)) else "-"
                if isinstance(cur, (int, float)) and isinstance(old, (int, float)):
                    d = cur - old
                    arrow = "up" if d > 0 else ("down" if d < 0 else "flat")
                    delta_s = f"{d:+.1%} [{arrow}]"
                else:
                    delta_s = "-"
                lines.append(f"| {name} | {cur_s} | {old_s} | {delta_s} |")

    lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Top-level evaluate_manifest entrypoint
# ----------------------------------------------------------------------


def _prompt_versions() -> Dict[str, str]:
    return {
        "technique_frame": TECHNIQUE_FRAME_PROMPT_VERSION,
        "behavior_visual": BEHAVIOR_VISUAL_PROMPT_VERSION,
        "claim_verifier": CLAIM_VERIFIER_PROMPT_VERSION,
    }


def _load_baseline(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"baseline file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_passes(arg: str) -> List[str]:
    arg = (arg or "all").strip().lower()
    if arg == "all":
        return list(ALL_PASSES)
    out = [p.strip() for p in arg.split(",") if p.strip()]
    for p in out:
        if p not in ALL_PASSES:
            raise ValueError(f"unknown pass {p!r}; valid: {ALL_PASSES + ('all',)}")
    return out


def _resolve_providers(arg: str) -> List[str]:
    out = [p.strip().lower() for p in (arg or "anthropic").split(",") if p.strip()]
    if not out:
        out = ["anthropic"]
    return out


def evaluate_manifest(
    *,
    manifest_path: Path,
    output_dir: Path,
    providers: List[str],
    passes: List[str],
    max_workers: int,
    compare_to: Optional[Path],
    threshold_pass_rate: float,
    threshold_regression: float,
    json_out: Path,
    markdown_out: Path,
    dry_run: bool,
    resume: bool,
    schema_path: Path = SCHEMA_DEFAULT,
) -> Dict[str, Any]:
    """Run the full eval and return the summary dict that gets written to
    `eval_summary.json`. The function is callable from tests for the dry-
    run + aggregation paths; the real API path is exercised only by the
    CLI / CI workflow."""

    manifest = validate_manifest(manifest_path, schema_path=schema_path)
    plans = build_plan(manifest, manifest_path)

    primary_provider = providers[0] if providers else "anthropic"
    try:
        primary_model = default_model_for(primary_provider)
    except VisionClientConfigError:
        primary_model = DEFAULT_SONNET_MODEL

    if dry_run:
        # Print the plan to stdout and exit; no API calls.
        print(f"[dry-run] manifest: {manifest_path}")
        print(f"[dry-run] providers: {providers}")
        print(f"[dry-run] passes: {passes}")
        total_frames = 0
        for plan in plans:
            print(f"[dry-run] clip {plan.clip_id}: {len(plan.frame_paths)} frames")
            for fp in plan.frame_paths:
                total_frames += 1
                for p in passes:
                    if p == "claims" and not schema_supports_claims(schema_path):
                        continue
                    print(f"[dry-run]   pass={p} frame={fp.name}")
        print(f"[dry-run] total frames: {total_frames}")
        return {
            "dry_run": True,
            "clips": [p.clip_id for p in plans],
            "frames": total_frames,
            "passes": passes,
        }

    # Build vision client for the primary provider once; the analyzers
    # share it so the cost telemetry is summed correctly.
    primary_client: Optional[VisionClient] = None
    try:
        primary_client = make_vision_client(primary_provider, model_id=primary_model)
    except VisionClientConfigError as e:
        print(f"[error] could not build vision client for {primary_provider}: {e}", file=sys.stderr)
        sys.exit(2)

    output_dir.mkdir(parents=True, exist_ok=True)

    frame_results: List[FrameResult] = []

    if "comprehensive" in passes:
        comp_analyzer = CMEComprehensiveAnalyzer(vision_client=primary_client)
        frame_results.extend(
            _run_comprehensive_pass(
                plans,
                analyzer=comp_analyzer,
                output_dir=output_dir,
                max_workers=max_workers,
                resume=resume,
            )
        )

    if "behavior" in passes:
        beh_analyzer = CMEBehaviorAnalyzer(vision_client=primary_client)
        frame_results.extend(
            _run_behavior_pass(
                plans,
                analyzer=beh_analyzer,
                output_dir=output_dir,
                max_workers=max_workers,
                resume=resume,
            )
        )

    if "claims" in passes:
        if not schema_supports_claims(schema_path):
            print("[skip] no claims labels in golden set yet (schema does not declare claims block)")
        else:
            print("[info] claims pass: schema supports claims, but no scoring implementation yet")

    agg = aggregate_results(frame_results=frame_results, passes_run=passes)

    baseline = None
    if compare_to is not None:
        baseline = _load_baseline(compare_to)

    verdict_reasons: List[str] = []
    overall_rate = agg["totals"]["pass_rate"]
    if overall_rate < threshold_pass_rate:
        verdict_reasons.append(
            f"overall pass rate {overall_rate:.1%} below threshold {threshold_pass_rate:.1%}"
        )

    if baseline is not None:
        b_rate = float((baseline.get("totals") or {}).get("pass_rate", 0.0) or 0.0)
        regression = b_rate - overall_rate
        if regression > threshold_regression:
            verdict_reasons.append(
                f"pass rate regressed {regression:.1%} vs baseline ({b_rate:.1%} -> {overall_rate:.1%}); "
                f"max allowed {threshold_regression:.1%}"
            )

    verdict = "fail" if verdict_reasons else "pass"

    summary: Dict[str, Any] = {
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256_file(manifest_path),
        "providers": providers,
        "primary_provider": primary_provider,
        "primary_model_id": primary_model,
        "prompt_versions": _prompt_versions(),
        "totals": agg["totals"],
        "by_clip": agg["by_clip"],
        "by_field": agg["by_field"],
        "thresholds": {
            "absolute": threshold_pass_rate,
            "regression": threshold_regression,
        },
        "baseline": baseline,
        "verdict": verdict,
        "verdict_reasons": verdict_reasons,
    }

    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    md = render_markdown(summary, frame_results)
    markdown_out.parent.mkdir(parents=True, exist_ok=True)
    markdown_out.write_text(md, encoding="utf-8")

    print(f"[info] wrote {json_out}")
    print(f"[info] wrote {markdown_out}")
    print(
        f"[info] verdict={verdict} pass_rate={overall_rate:.1%} "
        f"fields={agg['totals']['fields_passed']}/{agg['totals']['fields_evaluated']}"
    )
    if verdict_reasons:
        for r in verdict_reasons:
            print(f"[fail] {r}", file=sys.stderr)
    return summary


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Real eval harness for the CME vision analyzers.",
    )
    p.add_argument("--manifest", type=Path, default=MANIFEST_DEFAULT)
    p.add_argument("--providers", default="anthropic")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Default: eval_runs/<utc-timestamp>/",
    )
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--passes", default="all", choices=["comprehensive", "behavior", "claims", "all"])
    p.add_argument("--compare-to", type=Path, default=None)
    p.add_argument("--threshold-pass-rate", type=float, default=0.70)
    p.add_argument("--threshold-regression", type=float, default=0.05)
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument("--markdown-out", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--resume",
        action="store_true",
        help="Skip per-frame outputs that already exist on disk",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    output_dir = args.output_dir
    if output_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = REPO_ROOT / "eval_runs" / ts

    json_out = args.json_out or (output_dir / "eval_summary.json")
    markdown_out = args.markdown_out or (output_dir / "eval_summary.md")

    try:
        providers = _resolve_providers(args.providers)
        passes = _resolve_passes(args.passes)
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    if args.compare_to is not None and not args.compare_to.exists():
        print(f"[error] --compare-to path does not exist: {args.compare_to}", file=sys.stderr)
        return 2

    try:
        summary = evaluate_manifest(
            manifest_path=args.manifest,
            output_dir=output_dir,
            providers=providers,
            passes=passes,
            max_workers=args.max_workers,
            compare_to=args.compare_to,
            threshold_pass_rate=args.threshold_pass_rate,
            threshold_regression=args.threshold_regression,
            json_out=json_out,
            markdown_out=markdown_out,
            dry_run=args.dry_run,
            resume=args.resume,
        )
    except FileNotFoundError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    if summary.get("dry_run"):
        return 0
    return 0 if summary.get("verdict") == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
