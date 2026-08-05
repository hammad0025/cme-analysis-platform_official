"""
Provenance bundle helpers for CME analysis (roadmap step A5, minimum slice).

Provides:
- file_sha256: SHA-256 of a single file in fixed-size chunks.
- compute_bundle_hash: deterministic Merkle-ish root computed by hashing
  the sorted list of (relpath, file_sha256) pairs under a root directory.
- ffmpeg_version: best-effort capture of the local ffmpeg version line
  for inclusion in MANIFEST.json.
- iter_artifact_relpaths: stable ordering of artifact relative paths for
  the manifest.

The hashing function is intentionally simple and provider-agnostic so the
same number can be recomputed by a reviewer outside this codebase. The
algorithm is:

    for each file under root (sorted by relpath):
        update(relpath_bytes + b"\\0" + file_sha256_bytes + b"\\n")
    return hex_digest

Per-file digests use SHA-256 directly, not a separately keyed HMAC; this
is a pure-integrity manifest, not an authentication tag.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Iterable, List, Tuple


_CHUNK = 1024 * 1024  # 1 MiB; comfortable balance between syscalls and memory.


def file_sha256(path: Path) -> str:
    """Return hex SHA-256 of `path`. Reads in 1 MiB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_artifact_relpaths(
    root: Path,
    *,
    exclude_names: Iterable[str] = ("MANIFEST.json",),
    exclude_relpaths: Iterable[str] = (),
) -> List[str]:
    """Yield POSIX-style relative paths of every regular file under `root`,
    excluding `exclude_names` by basename and `exclude_relpaths` by exact
    POSIX relative path. Sorted for determinism.

    `exclude_relpaths` is how callers exclude large binary derivatives
    (e.g. ``audio/audio.wav``) from the deterministic bundle hash while
    still letting them sit on disk for inspection. Excluded relpaths
    must already use POSIX separators (``/``).
    """
    root = Path(root)
    out: List[str] = []
    excl_names = set(exclude_names or ())
    excl_rel = set(exclude_relpaths or ())
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name in excl_names:
            continue
        rel = p.relative_to(root).as_posix()
        if rel in excl_rel:
            continue
        out.append(rel)
    out.sort()
    return out


def file_digests(
    root: Path,
    relpaths: Iterable[str],
) -> List[Tuple[str, str]]:
    """Return [(relpath, sha256_hex)] sorted by relpath."""
    root = Path(root)
    pairs: List[Tuple[str, str]] = []
    for rel in relpaths:
        p = root / rel
        try:
            pairs.append((rel, file_sha256(p)))
        except OSError:
            continue
    pairs.sort(key=lambda x: x[0])
    return pairs


def compute_bundle_hash(
    root: Path,
    *,
    exclude_names: Iterable[str] = ("MANIFEST.json",),
    exclude_relpaths: Iterable[str] = (),
) -> Tuple[str, List[Tuple[str, str]]]:
    """Compute a Merkle-ish root over every artifact under `root`.

    Returns (bundle_sha256_hex, [(relpath, file_sha256_hex), ...]).

    Deterministic for the same files regardless of platform path
    separators because relpaths are normalized to POSIX form.

    `exclude_relpaths` accepts POSIX-form paths and is the right hook for
    excluding large binary derivatives (e.g. `audio/audio.wav`) from the
    deterministic text-level integrity surface."""
    relpaths = iter_artifact_relpaths(
        root,
        exclude_names=exclude_names,
        exclude_relpaths=exclude_relpaths,
    )
    pairs = file_digests(root, relpaths)
    h = hashlib.sha256()
    for rel, digest in pairs:
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(digest.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest(), pairs


def ffmpeg_version() -> str:
    """Return the first line of `ffmpeg -version` output, or empty string
    on failure. Used to record the extractor version in MANIFEST.json."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    line = (proc.stdout or proc.stderr or "").splitlines()
    return line[0].strip() if line else ""
