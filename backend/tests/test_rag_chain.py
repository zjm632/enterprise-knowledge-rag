from types import SimpleNamespace

from app.services.llm import MockChatProvider
from app.services.rag import REFUSAL_ANSWER, RAGService, build_answer_prompt, sanitize_answer
from app.services.retrieval import RetrievedChunk


class FakeRetriever:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def retrieve(self, knowledge_base_id, query, top_k, rewritten_query=None):
        self.calls.append((knowledge_base_id, query, top_k, rewritten_query))
        return self.results


class FakeLogs:
    def __init__(self):
        self.records = []

    def create(self, *args):
        self.records.append(args)


class EchoChat:
    model_name = "fake-chat"

    def answer(self, system_prompt, user_prompt):
        assert "[SOURCE 1]" in user_prompt
        return "根据引用来源，报销需要有效发票、费用说明和负责人审批记录。"


def make_service(results, chat=None):
    service = RAGService.__new__(RAGService)
    service.settings = SimpleNamespace(
        answer_min_score=0.22,
        answer_min_rerank_score=0.08,
        answer_min_evidence_count=1,
    )
    service.retriever = FakeRetriever(results)
    service.logs = FakeLogs()
    service.chat = chat or EchoChat()
    return service


def make_retrieved_chunk(content: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c1",
        document_name="handbook.md",
        content=content,
        chunk_index=0,
        page_number=None,
        vector_score=0.92,
        keyword_score=0.7,
        vector_rank_score=0.95,
        keyword_rank_score=0.9,
        rerank_score=0.5,
        final_score=0.82,
        sources="vector+keyword",
        matched_terms=["报销", "发票"],
    )


def test_rag_hits_document_answer_and_returns_citations():
    chunk = make_retrieved_chunk("员工报销需要提交有效发票、费用说明和直属负责人审批记录。")
    service = make_service([chunk])

    response = service.ask("kb1", "请问报销需要哪些材料？", 5)

    assert response["hit_knowledge_base"] is True
    assert "有效发票" in response["answer"]
    assert response["citations"]
    assert response["citations"][0]["document_name"] == "handbook.md"
    assert service.retriever.calls[0][3] != "请问报销需要哪些材料？"


def test_rag_stream_events_end_with_full_answer():
    chunk = make_retrieved_chunk("员工报销需要提交有效发票、费用说明和直属负责人审批记录。")
    service = make_service([chunk])

    events = list(service.ask_stream_events("kb1", "请问报销需要哪些材料？", 5))

    assert events[0]["event"] == "status"
    assert any(event["event"] == "token" for event in events)
    assert events[-1]["event"] == "done"
    assert "有效发票" in events[-1]["data"]["answer"]


def test_rag_refuses_unrelated_question_without_reliable_evidence():
    unrelated = RetrievedChunk(
        chunk_id="c2",
        document_name="handbook.md",
        content="员工报销需要提交有效发票。",
        chunk_index=1,
        page_number=None,
        vector_score=0.91,
        keyword_score=0.0,
        vector_rank_score=0.9,
        keyword_rank_score=0.0,
        rerank_score=0.0,
        final_score=0.5,
        sources="vector",
    )
    service = make_service([unrelated])

    response = service.ask("kb1", "火星基地什么时候开放？", 5)

    assert response["hit_knowledge_base"] is False
    assert response["answer"] == REFUSAL_ANSWER
    assert response["citations"] == []


def test_mock_answer_is_concise_and_preserves_required_qualifiers():
    chunk = make_retrieved_chunk(
        "## 报销流程\n\n"
        "员工报销需要在费用发生后 30 天内提交申请。"
        "申请材料包括有效发票、费用说明、项目归属和直属负责人审批记录。"
        "财务审核通过后，通常在 5 个工作日内完成打款。"
    )
    prompt = build_answer_prompt("报销需要哪些材料？", "报销 材料", [chunk])

    answer = MockChatProvider().answer("", prompt)

    assert "报销需要准备以下材料" in answer
    assert "有效发票" in answer
    assert "费用说明" in answer
    assert "项目归属" in answer
    assert "直属负责人审批记录" in answer
    assert "30 天" not in answer
    assert "5 个工作日" not in answer
    assert "回答规则" not in answer
    assert "SOURCE" not in answer
    assert "document=" not in answer
    assert "请查看下方引用来源" not in answer
    assert not answer.rstrip().endswith("不要为")


def test_sanitize_answer_removes_prompt_leakage():
    dirty = "报销需要有效发票。 □\n\n回答规则：不要使用外部知识。\n[SOURCE 1]\ndocument=handbook.md"

    answer = sanitize_answer(dirty)

    assert answer == "报销需要有效发票。"
    assert "□" not in answer
    assert "回答规则" not in answer
    assert "SOURCE" not in answer
    assert "document=" not in answer


def test_mock_company_question_returns_clean_summary():
    chunk = make_retrieved_chunk(
        "企业标准知识库（AI项目专用完整版） □ 一、企业基础信息 □ 1.0企业简介 "
        "智联科创信息技术有限公司，专注于企业数字化、人工智能应用落地、智能知识库系统、企业AI Agent、RAG智能问答系统研发与落地。"
        "主要服务政企、互联网、制造业企业数字化转型项目，主打AI私有化部署、企业内部智能问答、自动化办公助手解决方案。"
    )
    prompt = build_answer_prompt("这是什么公司", "什么 公司", [chunk])

    answer = MockChatProvider().answer("", prompt)

    assert "智联科创信息技术有限公司" in answer
    assert "专注于" in answer
    assert "主要业务" in answer
    assert "□" not in answer
    assert "1. 企业标准知识库" not in answer


def test_mock_process_question_extracts_only_target_flow():
    chunk = make_retrieved_chunk(
        "四、员工入职转正流程 "
        "1. 试用期时长 新员工统一试用期为3个月，表现优异者可申请提前转正，最短试用期不得低于1个月。"
        "2. 转正条件 试用期内无重大工作失误、无考勤违规、按时完成分配工作任务、通过部门负责人工作考核、通过HR合规审核。"
        "3. 转正流程步骤 员工提交转正申请 → 直属领导工作评价审核 → 部门负责人审批 → HR资质复核 → 总经理终审 → 正式转正生效。"
        "3. 上线流程 开发自测 → 提交测试环境 → 测试验收 → 代码评审 → 部署预发布环境 → 运维审核 → 正式上线。"
    )
    prompt = build_answer_prompt("转正流程", "转正 流程", [chunk])

    answer = MockChatProvider().answer("", prompt)

    assert "转正流程如下" in answer
    assert "员工提交转正申请" in answer
    assert "直属领导工作评价审核" in answer
    assert "部门负责人审批" in answer
    assert "HR资质复核" in answer
    assert "总经理终审" in answer
    assert "正式转正生效" in answer
    assert "试用期为3个月" not in answer
    assert "上线流程" not in answer
    assert "测试环境" not in answer
    assert "代码评审" not in answer


def test_mock_policy_question_stays_inside_requested_topic():
    chunk = make_retrieved_chunk(
        "三、费用报销管理制度 "
        "1. 报销时效要求 所有因公产生费用，必须在费用发生后30天内提交报销申请，逾期系统自动关闭，不予受理。"
        "2. 报销必备材料 有效合规发票、详细费用说明、项目归属说明、直属负责人审批记录。"
        "3. 报销审批流程 员工提交报销申请 → 直属负责人审批 → 财务审核 → 出纳打款。"
        "六、企业权限与白名单制度 "
        "1. 知识库访问权限 普通员工：仅可查看公开制度、考勤、报销、通用流程。"
    )
    prompt = build_answer_prompt("报销制度", "报销 制度", [chunk])

    answer = MockChatProvider().answer("", prompt)

    assert "报销制度包括" in answer
    assert "报销时效要求" in answer
    assert "报销必备材料" in answer
    assert "报销审批流程" in answer
    assert "1. 1." not in answer
    assert "企业权限" not in answer
    assert "白名单" not in answer
    assert "普通员工" not in answer
    assert "仅可查看公开制度" not in answer
