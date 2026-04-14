# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Đào Hồng Sơn (MSSV 2A202600462)
**Vai trò trong nhóm:** Trace & Docs Owner (Sprint 4)
**Nhóm:** Group 06 — E402
**Ngày nộp:** 2026-04-14

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `eval_trace.py`, `docs/system_architecture.md`,
  `docs/routing_decisions.md`, `docs/single_vs_multi_comparison.md`,
  `reports/group_report.md`, `artifacts/grading_run.jsonl`.
- Functions tôi implement/sửa trong `eval_trace.py`:
  `run_test_questions()`, `run_grading_questions()`, `analyze_traces()`,
  `compute_routing_accuracy()` (mới thêm), `compare_single_vs_multi()`,
  `save_eval_report()`, CLI entry.

**Cách công việc của tôi kết nối với phần của thành viên khác:**
Tôi là "khách hàng cuối" của `graph.py` (Quân) và các `workers/*` (Phú,
Định, Khang) — tôi không sửa logic routing hay worker, chỉ gọi
`run_graph(task)` rồi đọc `state` trả về để lưu trace và tính metric. Vì
vậy, contract `AgentState` mà Sprint 1 định nghĩa là interface tôi phụ
thuộc hoàn toàn. Tôi cũng là người duy nhất đụng tới `artifacts/` nên bug
trace-overwrite chỉ có tôi phát hiện.

**Bằng chứng:**
- 15 file trace trong `artifacts/traces/` có filename dạng
  `run_<timestamp>_q01.json` … `_q15.json` — là format do patch của tôi tạo
  ra (append `question_id` vào `run_id`).
- `artifacts/eval_report.json` do tôi generate, chứa field
  `routing_accuracy.routing_match = "14/15"` — là metric mới tôi thêm
  trong Sprint 4.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Thêm hàm `compute_routing_accuracy()` riêng biệt so sánh
`supervisor_route` thực tế (trong trace) với `expected_route` (trong
`test_questions.json`), thay vì chỉ báo cáo `routing_distribution` như gợi
ý ban đầu trong `analyze_traces()`.

**Các lựa chọn thay thế:**
- (a) Chỉ tính distribution (bao nhiêu câu đi vào mỗi worker) — dễ, đã có
  sẵn. Nhưng không trả lời được "route có đúng không?".
- (b) Gọi LLM judge để chấm câu trả lời cuối — đắt, chạy 15 câu tốn nhiều
  token, không cần thiết ở tầng routing.
- (c) Function riêng so khớp route vs expected_route — nhẹ, deterministic,
  output list `mismatches` dùng trực tiếp để viết `routing_decisions.md`.

**Lý do:** Scoring rubric (SCORING.md §2.2) yêu cầu ≥3 routing decisions
thực tế có kết quả đúng/sai; không có hàm này tôi sẽ phải so tay 15 trace.
Quan trọng hơn, nó sinh ra bằng chứng cụ thể cho câu q02 mismatch → dẫn
trực tiếp vào mục "cải tiến" trong `single_vs_multi_comparison.md`.

**Trade-off đã chấp nhận:** Hàm chỉ check route layer, không chấm nội dung
answer. Cần một `accuracy_judge()` riêng cho phần đó (ngoài scope Sprint 4
của tôi).

**Bằng chứng từ trace/code:**

```python
# eval_trace.py — hàm tôi mới thêm
def compute_routing_accuracy(traces_dir, questions_file):
    ...
    for qid, q in questions.items():
        expected = q.get("expected_route")
        actual = traces[qid].get("supervisor_route", "")
        if actual == expected: match += 1
        else: mismatches.append({"id": qid, "expected": expected, "actual": actual})
    return {"routing_match": f"{match}/{total}", ...}
```

```json
// artifacts/eval_report.json (output thực)
"routing_accuracy": {
  "routing_match": "14/15",
  "routing_match_rate": 0.933,
  "mismatches": [
    {"id": "q02", "expected": "retrieval_worker", "actual": "policy_tool_worker"}
  ]
}
```

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** `analyze_traces()` crash `UnicodeDecodeError 'charmap' codec`
khi đọc file trace; **và** 15 trace file bị overwrite lẫn nhau, chỉ còn 2
file trong `artifacts/traces/` sau khi chạy end-to-end.

**Symptom (pipeline làm gì sai?):**
- Terminal: `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81`
  khi `json.load(f)` trong `analyze_traces`.
- `ls artifacts/traces/` chỉ trả về 2 file (`run_20260414_113205.json`,
  `run_20260414_113217.json`) thay vì 15 — analytics vì thế chỉ thấy 2
  route, không phản ánh đúng 15-question run.

**Root cause (lỗi nằm ở đâu):**
- Encoding bug: trên Windows, `open(path)` mặc định `cp1252`, không đọc
  được chuỗi tiếng Việt trong trace.
- Overwrite bug: `graph.py::make_initial_state` đặt
  `run_id = f"run_{now.strftime('%Y%m%d_%H%M%S')}"`. Khi 15 câu chạy trong
  cùng 1 giây, mọi run có cùng `run_id` → cùng filename →
  `save_trace` ghi đè liên tục.

**Cách sửa:**
- Encoding: thêm `encoding="utf-8"` vào `open(...)` trong `analyze_traces`.
- Overwrite: tại `run_test_questions()` và `run_grading_questions()`, ngay
  sau khi gọi `run_graph`, tôi append `question_id` vào `run_id`:
  `result["run_id"] = f"{result['run_id']}_{q_id}"`. Không đụng `graph.py`
  vì đó là territory của Quân — fix ở tầng eval là đủ.

**Bằng chứng trước/sau:**

```
# Trước (terminal)
✅ Done. 15 / 15 succeeded.
Traceback ...
UnicodeDecodeError: 'charmap' codec can't decode byte 0x81 ...
$ ls artifacts/traces/ | wc -l
2

# Sau
✅ Done. 15 / 15 succeeded.
📊 Trace Analysis:
  total_traces: 15
  routing_distribution: retrieval_worker 8/15, policy_tool_worker 7/15
$ ls artifacts/traces/ | wc -l
15
```

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?** Biến trace từ "dữ liệu thô" thành "bằng
chứng có thể cite trong docs". Mọi con số trong 3 file docs/ và group
report đều có nguồn cụ thể trong `artifacts/eval_report.json` hoặc trace
file, không bịa.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?** `confidence` trong báo cáo
vẫn là placeholder 0.75 — tôi chưa kịp phối hợp với Phú (synthesis owner)
để gắn confidence thật từ cosine score. Metric `avg_confidence` vì thế hơi
"rỗng".

**Nhóm phụ thuộc vào tôi ở đâu?** Toàn bộ deliverable bắt buộc thuộc
Sprint 4 (grading run log, 3 docs, group report, eval end-to-end). Nếu
`eval_trace.py` không chạy được hay trace thiếu field, các thành viên khác
không có cách độc lập sinh log đủ format SCORING.md yêu cầu — nhóm sẽ mất
điểm hạng mục Grading (30đ) và Documentation (10đ).

**Phần tôi phụ thuộc vào thành viên khác:** Cần `AgentState` có đủ field
(`supervisor_route`, `route_reason`, `workers_called`, `mcp_tools_used`,
`hitl_triggered`, `latency_ms`) — nếu một field thiếu, trace log bị mất
column, bị trừ 20%/câu theo rubric. May mắn Quân đã define đầy đủ từ
Sprint 1.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ viết `accuracy_judge(trace, expected_answer)` dùng LLM chấm
semantic match giữa `final_answer` và `expected_answer` trong
`test_questions.json`, output score 0/0.5/1. Lý do từ trace: hiện tại
`single_vs_multi_comparison.md` dùng multi-hop accuracy 67% là đếm tay
2/3 câu (q13, q15) — không scale. Với judge, tôi có số liệu accuracy tự
động cho cả 15 câu, đồng thời detect được hallucination để feed vào mục
"abstain rate" trong report.

---

*Lưu file này với tên: `reports/individual/dao_hong_son.md`*
