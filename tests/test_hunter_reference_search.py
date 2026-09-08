from backend.lambda_functions.cme_claim_verifier import hunter_methodology_context_for_claim
from backend.lambda_functions.cme_hunter_reference_search import (
    CONTEXT_HEADER,
    hunter_reference_context_for_claim,
    load_hunter_reference_index,
    search_hunter_references,
)


def test_packaged_hunter_index_is_available():
    records = load_hunter_reference_index()

    assert len(records) > 100
    assert any("Range of Motion" in str(r.get("source_file")) for r in records)


def test_cervical_rom_query_retrieves_instrument_context():
    results = search_hunter_references(
        "cervical range of motion goniometer inclinometer six planes",
        claim_id="cervical_rom",
        max_results=5,
    )
    joined = " ".join(
        f"{r.get('title')} {r.get('source_file')} {r.get('excerpt')}" for r in results
    ).lower()

    assert results
    assert "range of motion" in joined or "rom" in joined
    assert "goniometer" in joined or "inclinometer" in joined


def test_romberg_context_is_compact_and_specific():
    ctx = hunter_reference_context_for_claim(
        "romberg",
        "The report states Romberg was negative.",
    )

    assert CONTEXT_HEADER in ctx
    assert "romberg" in ctx.lower()
    assert len(ctx) < 2800


def test_claim_verifier_context_includes_retrieved_corpus():
    ctx = hunter_methodology_context_for_claim(
        "cervical_rom",
        "Cervical range of motion is normal in all planes.",
    )

    assert "HUNTER / EXAM STANDARDS" in ctx
    assert CONTEXT_HEADER in ctx
    assert "goniometer" in ctx.lower() or "inclinometer" in ctx.lower()
