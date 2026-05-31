import json
import sys
import time
from pathlib import Path

import requests


API_BASE = "http://localhost:8000/api"


def main() -> int:
    cases_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("eval_cases.json")
    report_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("eval_report.json")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    results = []
    hit_count = 0
    citation_count = 0
    refusal_count = 0
    total_latency = 0
    login_response = requests.post(
        f"{API_BASE}/auth/login",
        json={"username": "admin", "password": "admin123"},
        timeout=30,
    )
    login_response.raise_for_status()
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    for case in cases:
        started = time.perf_counter()
        response = requests.post(
            f"{API_BASE}/knowledge-bases/{case['knowledge_base_id']}/ask",
            json={"question": case["question"], "top_k": case.get("top_k", 8)},
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        expected = case.get("expected_keyword", "")
        retrieval_hit = any(expected.lower() in item.get("document_name", "").lower() or expected.lower() in str(item).lower() for item in data["retrieval_results"]) if expected else data["hit_knowledge_base"]
        has_citation = bool(data["citations"])
        hit_count += int(retrieval_hit)
        citation_count += int(has_citation)
        refusal_count += int(not data["hit_knowledge_base"])
        total_latency += elapsed_ms
        results.append(
            {
                "question": case["question"],
                "retrieval_hit": retrieval_hit,
                "has_citation": has_citation,
                "refused": not data["hit_knowledge_base"],
                "latency_ms": elapsed_ms,
                "answer": data["answer"],
            }
        )

    total = max(len(cases), 1)
    report = {
        "case_count": len(cases),
        "retrieval_hit_rate": round(hit_count / total, 4),
        "refusal_rate": round(refusal_count / total, 4),
        "citation_rate": round(citation_count / total, 4),
        "avg_latency_ms": round(total_latency / total, 2),
        "results": results,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
