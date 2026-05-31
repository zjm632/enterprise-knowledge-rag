from app.services.rag import REFUSAL_ANSWER, has_reliable_evidence


def test_no_evidence_refusal_contract():
    assert has_reliable_evidence([], 0.2) is False
    assert REFUSAL_ANSWER == "知识库中未找到可靠依据。"
