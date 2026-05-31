from app.services.chunking import ParsedSection, split_sections_into_chunks


def test_split_sections_into_chunks_keeps_metadata_and_overlap():
    text = "腾讯云企业知识库支持文档检索。" * 80
    chunks = split_sections_into_chunks([ParsedSection(text=text, page_number=3)], chunk_size=260, overlap=30)

    assert len(chunks) > 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].page_number == 3
    assert chunks[0].char_length <= 260
    assert chunks[1].chunk_index == 1
    assert chunks[0].token_estimate > 0


def test_split_sections_merges_short_tail_fragments():
    text = "报销流程需要发票、费用说明和负责人审批。\n\n短句"
    chunks = split_sections_into_chunks([ParsedSection(text=text, paragraph_index=1)], chunk_size=240, overlap=20, min_chunk_size=80)

    assert len(chunks) == 1
    assert "短句" in chunks[0].content
    assert chunks[0].char_length <= 240
