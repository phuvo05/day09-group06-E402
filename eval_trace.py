"""
eval_trace.py — Trace Evaluation & Comparison
Sprint 4: Chạy pipeline với test questions, phân tích trace, so sánh single vs multi.

Chạy:
    python eval_trace.py                  # Chạy 15 test questions
    python eval_trace.py --grading        # Chạy grading questions (sau 17:00)
    python eval_trace.py --analyze        # Phân tích trace đã có
    python eval_trace.py --compare        # So sánh single vs multi

Outputs:
    artifacts/traces/          — trace của từng câu hỏi
    artifacts/grading_run.jsonl — log câu hỏi chấm điểm
    artifacts/eval_report.json  — báo cáo tổng kết
"""

import json
import os
import sys
import argparse
from datetime import datetime
from typing import Optional

# Import graph
sys.path.insert(0, os.path.dirname(__file__))
from graph import run_graph, save_trace


# ─────────────────────────────────────────────
# 1. Run Pipeline on Test Questions
# ─────────────────────────────────────────────

def run_test_questions(questions_file: str = "data/test_questions.json") -> list:
    """
    Chạy pipeline với danh sách câu hỏi, lưu trace từng câu.

    Returns:
        list of (question, result) tuples
    """
    with open(questions_file, encoding="utf-8") as f:
        questions = json.load(f)

    print(f"\n📋 Running {len(questions)} test questions from {questions_file}")
    print("=" * 60)

    results = []
    for i, q in enumerate(questions, 1):
        question_text = q["question"]
        q_id = q.get("id", f"q{i:02d}")

        print(f"[{i:02d}/{len(questions)}] {q_id}: {question_text[:65]}...")

        try:
            result = run_graph(question_text)
            result["question_id"] = q_id
            # Ensure unique trace filename per question (avoid overwrite when timestamps collide)
            result["run_id"] = f"{result.get('run_id','run')}_{q_id}"

            # Save individual trace
            trace_file = save_trace(result, f"artifacts/traces")
            print(f"  ✓ route={result.get('supervisor_route', '?')}, "
                  f"conf={result.get('confidence', 0):.2f}, "
                  f"{result.get('latency_ms', 0)}ms")

            results.append({
                "id": q_id,
                "question": question_text,
                "expected_answer": q.get("expected_answer", ""),
                "expected_sources": q.get("expected_sources", []),
                "difficulty": q.get("difficulty", "unknown"),
                "category": q.get("category", "unknown"),
                "result": result,
            })

        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            results.append({
                "id": q_id,
                "question": question_text,
                "error": str(e),
                "result": None,
            })

    print(f"\n✅ Done. {sum(1 for r in results if r.get('result'))} / {len(results)} succeeded.")
    return results


# ─────────────────────────────────────────────
# 2. Run Grading Questions (Sprint 4)
# ─────────────────────────────────────────────

def run_grading_questions(questions_file: str = "data/grading_questions.json") -> str:
    """
    Chạy pipeline với grading questions và lưu JSONL log.
    Dùng cho chấm điểm nhóm (chạy sau khi grading_questions.json được public lúc 17:00).

    Returns:
        path tới grading_run.jsonl
    """
    if not os.path.exists(questions_file):
        print(f"❌ {questions_file} chưa được public (sau 17:00 mới có).")
        return ""

    with open(questions_file, encoding="utf-8") as f:
        questions = json.load(f)

    os.makedirs("artifacts", exist_ok=True)
    output_file = "artifacts/grading_run.jsonl"

    print(f"\n🎯 Running GRADING questions — {len(questions)} câu")
    print(f"   Output → {output_file}")
    print("=" * 60)

    with open(output_file, "w", encoding="utf-8") as out:
        for i, q in enumerate(questions, 1):
            q_id = q.get("id", f"gq{i:02d}")
            question_text = q["question"]
            print(f"[{i:02d}/{len(questions)}] {q_id}: {question_text[:65]}...")

            try:
                result = run_graph(question_text)
                record = {
                    "id": q_id,
                    "question": question_text,
                    "answer": result.get("final_answer", "PIPELINE_ERROR: no answer"),
                    "sources": result.get("retrieved_sources", []),
                    "supervisor_route": result.get("supervisor_route", ""),
                    "route_reason": result.get("route_reason", ""),
                    "workers_called": result.get("workers_called", []),
                    "mcp_tools_used": [t.get("mcp_tool_called") for t in result.get("mcp_tools_used", [])],
                    "confidence": result.get("confidence", 0.0),
                    "hitl_triggered": result.get("hitl_triggered", False),
                    "latency_ms": result.get("latency_ms"),
                    "timestamp": datetime.now().isoformat(),
                }
                print(f"  ✓ route={record['supervisor_route']}, conf={record['confidence']:.2f}")
            except Exception as e:
                record = {
                    "id": q_id,
                    "question": question_text,
                    "answer": f"PIPELINE_ERROR: {e}",
                    "sources": [],
                    "supervisor_route": "error",
                    "route_reason": str(e),
                    "workers_called": [],
                    "mcp_tools_used": [],
                    "confidence": 0.0,
                    "hitl_triggered": False,
                    "latency_ms": None,
                    "timestamp": datetime.now().isoformat(),
                }
                print(f"  ✗ ERROR: {e}")

            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\n✅ Grading log saved → {output_file}")
    return output_file


# ─────────────────────────────────────────────
# 3. Analyze Traces
# ─────────────────────────────────────────────

def analyze_traces(traces_dir: str = "artifacts/traces") -> dict:
    """
    Đọc tất cả trace files và tính metrics tổng hợp.

    Metrics:
    - routing_distribution: % câu đi vào mỗi worker
    - avg_confidence: confidence trung bình
    - avg_latency_ms: latency trung bình
    - mcp_usage_rate: % câu có MCP tool call
    - hitl_rate: % câu trigger HITL
    - source_coverage: các tài liệu nào được dùng nhiều nhất

    Returns:
        dict of metrics
    """
    if not os.path.exists(traces_dir):
        print(f"⚠️  {traces_dir} không tồn tại. Chạy run_test_questions() trước.")
        return {}

    trace_files = [f for f in os.listdir(traces_dir) if f.endswith(".json")]
    if not trace_files:
        print(f"⚠️  Không có trace files trong {traces_dir}.")
        return {}

    traces = []
    for fname in trace_files:
        with open(os.path.join(traces_dir, fname), encoding="utf-8") as f:
            traces.append(json.load(f))

    # Compute metrics
    routing_counts = {}
    confidences = []
    latencies = []
    mcp_calls = 0
    hitl_triggers = 0
    source_counts = {}

    for t in traces:
        route = t.get("supervisor_route", "unknown")
        routing_counts[route] = routing_counts.get(route, 0) + 1

        conf = t.get("confidence", 0)
        if conf:
            confidences.append(conf)

        lat = t.get("latency_ms")
        if lat:
            latencies.append(lat)

        if t.get("mcp_tools_used"):
            mcp_calls += 1

        if t.get("hitl_triggered"):
            hitl_triggers += 1

        for src in t.get("retrieved_sources", []):
            source_counts[src] = source_counts.get(src, 0) + 1

    total = len(traces)
    metrics = {
        "total_traces": total,
        "routing_distribution": {k: f"{v}/{total} ({100*v//total}%)" for k, v in routing_counts.items()},
        "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "mcp_usage_rate": f"{mcp_calls}/{total} ({100*mcp_calls//total}%)" if total else "0%",
        "hitl_rate": f"{hitl_triggers}/{total} ({100*hitl_triggers//total}%)" if total else "0%",
        "top_sources": sorted(source_counts.items(), key=lambda x: -x[1])[:5],
    }

    return metrics


# ─────────────────────────────────────────────
# 4. Compare Single vs Multi Agent
# ─────────────────────────────────────────────

def compute_routing_accuracy(
    traces_dir: str = "artifacts/traces",
    questions_file: str = "data/test_questions.json",
) -> dict:
    """So sánh supervisor_route thực tế vs expected_route trong test_questions."""
    if not (os.path.exists(traces_dir) and os.path.exists(questions_file)):
        return {}
    with open(questions_file, encoding="utf-8") as f:
        questions = {q["id"]: q for q in json.load(f)}
    traces = {}
    for fname in os.listdir(traces_dir):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(traces_dir, fname), encoding="utf-8") as f:
            t = json.load(f)
        qid = t.get("question_id")
        if qid:
            traces[qid] = t
    match, total, mismatches = 0, 0, []
    for qid, q in questions.items():
        expected = q.get("expected_route")
        t = traces.get(qid)
        if not (expected and t):
            continue
        total += 1
        actual = t.get("supervisor_route", "")
        if actual == expected:
            match += 1
        else:
            mismatches.append({"id": qid, "expected": expected, "actual": actual})
    return {
        "routing_match": f"{match}/{total}",
        "routing_match_rate": round(match / total, 3) if total else 0,
        "mismatches": mismatches,
    }


def compare_single_vs_multi(
    multi_traces_dir: str = "artifacts/traces",
    day08_results_file: Optional[str] = None,
) -> dict:
    """
    So sánh Day 08 (single agent RAG) vs Day 09 (multi-agent).
    Baseline Day 08 lấy từ eval.py của lab Day 08 (hoặc giả lập nếu chưa có).
    """
    multi_metrics = analyze_traces(multi_traces_dir)
    routing_acc = compute_routing_accuracy(multi_traces_dir)

    # Baseline Day 08 — số thật từ lab Day 08 của nhóm 06-E402.
    # Nguồn: day08-group06-E402/docs/tuning-log.md (scorecard Variant 1: dense + rerank)
    #        day08-group06-E402/logs/grading_run.json (10 câu grading)
    #        day08-group06-E402/reports/group_report.md
    day08_baseline = {
        "source": "day08-group06-E402 (tuning-log.md + grading_run.json)",
        "pipeline": "single-agent RAG: dense retrieval + cross-encoder rerank, gpt-4o-mini",
        "total_questions_grading": 10,
        "grading_raw_score": "98/98",
        "faithfulness": "5.00/5",
        "answer_relevance": "4.60/5",
        "context_recall": "5.00/5",
        "completeness": "3.80/5",
        "abstain_rate": "1/10 (10%)",
        "abstain_example": "gq07 (Approval Matrix) — abstain đúng khi chunk thiếu alias",
        "rerank_latency_overhead_ms": 1200,
        "avg_latency_ms_est": 1850,
        "multi_hop_accuracy": "N/A (Day 08 không phân loại multi-hop)",
        "routing_visibility": "N/A (single-agent, không có supervisor)",
        "weakest_questions_baseline": ["q07 (alias mapping)", "q09 (ERR-403 out-of-scope)", "q10 (VIP refund)"],
    }

    if day08_results_file and os.path.exists(day08_results_file):
        with open(day08_results_file) as f:
            day08_baseline = json.load(f)

    comparison = {
        "generated_at": datetime.now().isoformat(),
        "day08_single_agent": day08_baseline,
        "day09_multi_agent": multi_metrics,
        "routing_accuracy": routing_acc,
        "analysis": {
            "routing_visibility": "Day 09 có route_reason cho từng câu → dễ debug hơn Day 08",
            "latency_delta": "TODO: Điền delta latency thực tế",
            "accuracy_delta": "TODO: Điền delta accuracy thực tế từ grading",
            "debuggability": "Multi-agent: có thể test từng worker độc lập. Single-agent: không thể.",
            "mcp_benefit": "Day 09 có thể extend capability qua MCP không cần sửa core. Day 08 phải hard-code.",
        },
    }

    return comparison


# ─────────────────────────────────────────────
# 5. Save Eval Report
# ─────────────────────────────────────────────

def save_eval_report(comparison: dict) -> str:
    """Lưu báo cáo eval tổng kết ra file JSON."""
    os.makedirs("artifacts", exist_ok=True)
    output_file = "artifacts/eval_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
    return output_file


# ─────────────────────────────────────────────
# 6. CLI Entry Point
# ─────────────────────────────────────────────

def print_metrics(metrics: dict):
    """Print metrics đẹp."""
    if not metrics:
        return
    print("\n📊 Trace Analysis:")
    for k, v in metrics.items():
        if isinstance(v, list):
            print(f"  {k}:")
            for item in v:
                print(f"    • {item}")
        elif isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk}: {vv}")
        else:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Day 09 Lab — Trace Evaluation")
    parser.add_argument("--grading", action="store_true", help="Run grading questions")
    parser.add_argument("--analyze", action="store_true", help="Analyze existing traces")
    parser.add_argument("--compare", action="store_true", help="Compare single vs multi")
    parser.add_argument("--test-file", default="data/test_questions.json", help="Test questions file")
    args = parser.parse_args()

    if args.grading:
        # Chạy grading questions
        log_file = run_grading_questions()
        if log_file:
            print(f"\n✅ Grading log: {log_file}")
            print("   Nộp file này trước 18:00!")

    elif args.analyze:
        # Phân tích traces — chỉ in ra terminal, KHÔNG ghi file nào
        metrics = analyze_traces()
        print_metrics(metrics)

        # Routing accuracy (expected vs actual)
        routing_acc = compute_routing_accuracy()
        if routing_acc:
            print("\n🎯 Routing Accuracy (expected vs actual):")
            print(f"  match      : {routing_acc.get('routing_match')}")
            print(f"  match_rate : {routing_acc.get('routing_match_rate')}")
            mm = routing_acc.get("mismatches", [])
            print(f"  mismatches : {len(mm)}")
            for m in mm:
                print(f"    ✗ {m['id']}: expected={m['expected']}, actual={m['actual']}")

        # Per-trace summary bảng ngắn
        traces_dir = "artifacts/traces"
        if os.path.exists(traces_dir):
            files = sorted(f for f in os.listdir(traces_dir) if f.endswith(".json"))
            print(f"\n📝 Per-trace summary ({len(files)} traces):")
            print(f"  {'qid':<5} {'route':<22} {'workers':<45} {'src':<22} {'conf':<5} {'hitl':<5} {'lat_ms':<7}")
            print(f"  {'-'*5} {'-'*22} {'-'*45} {'-'*22} {'-'*5} {'-'*5} {'-'*7}")
            for fname in files:
                with open(os.path.join(traces_dir, fname), encoding="utf-8") as f:
                    t = json.load(f)
                qid = t.get("question_id", fname[:6])
                route = t.get("supervisor_route", "?")
                workers = ",".join(t.get("workers_called", []))
                srcs = ",".join(t.get("retrieved_sources", []))[:22]
                conf = t.get("confidence", 0)
                hitl = "Y" if t.get("hitl_triggered") else "-"
                lat = t.get("latency_ms", 0) or 0
                print(f"  {qid:<5} {route:<22} {workers[:45]:<45} {srcs:<22} {conf:<5.2f} {hitl:<5} {lat:<7}")

        # Day 08 baseline comparison (in-memory, không save)
        print("\n📈 Day 08 vs Day 09 (snapshot, không ghi file):")
        comp = compare_single_vs_multi()
        d08 = comp.get("day08_single_agent", {})
        d09 = comp.get("day09_multi_agent", {})
        rows = [
            ("avg_confidence", d08.get("avg_confidence"), d09.get("avg_confidence")),
            ("avg_latency_ms", d08.get("avg_latency_ms"), d09.get("avg_latency_ms")),
            ("abstain/hitl_rate", d08.get("abstain_rate"), d09.get("hitl_rate")),
            ("multi_hop_accuracy", d08.get("multi_hop_accuracy"), "—"),
        ]
        print(f"  {'metric':<22} {'Day08':<18} {'Day09':<18}")
        for m, a, b in rows:
            print(f"  {m:<22} {str(a):<18} {str(b):<18}")

    elif args.compare:
        # So sánh single vs multi
        comparison = compare_single_vs_multi()
        report_file = save_eval_report(comparison)
        print(f"\n📊 Comparison report saved → {report_file}")
        print("\n=== Day 08 vs Day 09 ===")
        for k, v in comparison.get("analysis", {}).items():
            print(f"  {k}: {v}")

    else:
        # Default: chạy test questions
        results = run_test_questions(args.test_file)

        # Phân tích trace
        metrics = analyze_traces()
        print_metrics(metrics)

        # Lưu báo cáo
        comparison = compare_single_vs_multi()
        report_file = save_eval_report(comparison)
        print(f"\n📄 Eval report → {report_file}")
        print("\n✅ Sprint 4 complete!")
