"""Tests for backend.lambda_functions.cme_provenance.

Verifies that compute_bundle_hash is deterministic, sensitive to content
changes, and correctly excludes named files."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.lambda_functions.cme_provenance import (  # noqa: E402
    compute_bundle_hash,
    file_sha256,
    iter_artifact_relpaths,
)


def _seed_dir(root: Path) -> None:
    (root / "a.txt").write_text("alpha\n", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "b.json").write_text('{"k":"v"}\n', encoding="utf-8")
    (sub / "c.bin").write_bytes(b"\x00\x01\x02")


def test_bundle_hash_is_deterministic_and_excludes_manifest(tmp_path: Path):
    _seed_dir(tmp_path)
    (tmp_path / "MANIFEST.json").write_text('{"will be excluded": true}', encoding="utf-8")

    h1, pairs1 = compute_bundle_hash(tmp_path)
    h2, pairs2 = compute_bundle_hash(tmp_path)

    assert h1 == h2, "bundle hash must be deterministic"
    rels1 = {rel for rel, _ in pairs1}
    assert "MANIFEST.json" not in rels1
    assert {"a.txt", "sub/b.json", "sub/c.bin"} <= rels1


def test_bundle_hash_changes_when_a_file_changes(tmp_path: Path):
    _seed_dir(tmp_path)
    h1, _ = compute_bundle_hash(tmp_path)
    (tmp_path / "a.txt").write_text("beta\n", encoding="utf-8")
    h2, _ = compute_bundle_hash(tmp_path)
    assert h1 != h2, "any artifact change must change the bundle hash"


def test_iter_artifact_relpaths_sorted_and_posix(tmp_path: Path):
    _seed_dir(tmp_path)
    rels = iter_artifact_relpaths(tmp_path)
    assert rels == sorted(rels)
    assert all("\\" not in r for r in rels)


def test_file_sha256_matches_known_value(tmp_path: Path):
    p = tmp_path / "x.txt"
    p.write_text("hello", encoding="utf-8")
    # SHA-256("hello") = 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
    assert (
        file_sha256(p)
        == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_bundle_hash_extra_exclusions_respected(tmp_path: Path):
    _seed_dir(tmp_path)
    (tmp_path / "render.html").write_text("<html></html>", encoding="utf-8")
    h_with_render, pairs_with = compute_bundle_hash(tmp_path)
    h_excl_render, pairs_excl = compute_bundle_hash(
        tmp_path, exclude_names=("MANIFEST.json", "render.html")
    )
    assert h_with_render != h_excl_render
    assert "render.html" in {rel for rel, _ in pairs_with}
    assert "render.html" not in {rel for rel, _ in pairs_excl}


def test_bundle_hash_exclude_relpaths_skips_binary_derivatives(tmp_path: Path):
    """`exclude_relpaths` lets callers drop a specific POSIX-relpath
    artifact from the bundle hash (used by analyze_cme_full to exclude
    audio/audio.wav from the deterministic text-level integrity surface
    while still letting it sit on disk for inspection)."""
    _seed_dir(tmp_path)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    wav_path = audio_dir / "audio.wav"
    wav_path.write_bytes(b"RIFFfakeWAVE" * 100)
    transcript_path = audio_dir / "transcript.json"
    transcript_path.write_text("{}", encoding="utf-8")

    h_with_wav, pairs_with = compute_bundle_hash(tmp_path)
    h_excl_wav, pairs_excl = compute_bundle_hash(
        tmp_path, exclude_relpaths=("audio/audio.wav",)
    )
    rels_with = {rel for rel, _ in pairs_with}
    rels_excl = {rel for rel, _ in pairs_excl}

    assert h_with_wav != h_excl_wav, "excluding audio.wav must change the bundle hash"
    assert "audio/audio.wav" in rels_with
    assert "audio/audio.wav" not in rels_excl
    # transcript artifacts must remain in the hash regardless
    assert "audio/transcript.json" in rels_excl
