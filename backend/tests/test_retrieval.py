from types import SimpleNamespace

from app.services.retrieval import merge_and_rerank


def chunk(chunk_id, content):
    return SimpleNamespace(
        id=chunk_id,
        document_name="handbook.md",
        content=content,
        chunk_index=0,
        page_number=None,
    )


def test_merge_and_rerank_prefers_combined_signal():
    strong = chunk("1", "报销流程 需要 发票 和 审批")
    weak = chunk("2", "公司年假制度")

    results = merge_and_rerank(
        "报销 发票",
        [{"chunk": weak, "score": 0.5}, {"chunk": strong, "score": 0.45}],
        [{"chunk": strong, "score": 0.8}],
        2,
    )

    assert results[0].chunk_id == "1"
    assert results[0].keyword_score == 0.8
    assert "keyword" in results[0].sources
