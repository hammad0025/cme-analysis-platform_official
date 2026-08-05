import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "tests/fixtures/golden_set/manifest.json"
SCHEMA = REPO / "tests/fixtures/golden_set/schema/manifest.schema.json"


def _basic_validate_manifest(data: dict) -> None:
    assert data.get("schema_version") == 1
    clips = data.get("clips")
    assert isinstance(clips, list) and len(clips) >= 1
    for c in clips:
        assert "id" in c and c["id"]
        assert "frames_dir" in c
        assert "eval_frame_glob" in c
        assert isinstance(c.get("expected"), dict)


def test_every_clip_has_non_empty_expected():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for c in data["clips"]:
        expected = c.get("expected")
        assert isinstance(expected, dict), f"clip {c.get('id')!r} has no expected dict"
        assert expected, (
            f"clip {c.get('id')!r} has empty expected{{}}; v1 golden set requires "
            "at least one human-curated label per clip (see docs/golden_set_curation.md)"
        )


def test_manifest_loads_and_matches_schema_shape():
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    _basic_validate_manifest(raw)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema.get("title") == "CME golden set manifest"


def test_example_frames_exist():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = MANIFEST.parent
    for c in data["clips"]:
        d = base / c["frames_dir"]
        assert d.is_dir(), f"missing {d}"
        assert list(d.glob(c["eval_frame_glob"])), f"no match for {c['eval_frame_glob']}"
