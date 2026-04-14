# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Đào Hồng Sơn (MSSV 2A202600462)
**Vai trò trong nhóm:** Trace & Docs Owner (Sprint 4)
**Nhóm:** Group 06 — E402
**Ngày nộp:** 2026-04-14

---

## 1. Tôi phụ trách phần nào?

| Task | File/Function | Trạng thái |
|------|--------------|------------|
| Implement `eval_trace.py` | `eval_trace.py` | ✅ Hoàn thành |
| Implement `analyze_trace()` và `compare_single_vs_multi()` | `eval_trace.py` | ✅ Hoàn thành |
| Điền `docs/routing_decisions.md` | `docs/routing_decisions.md` | ✅ Hoàn thành |
| Điền `docs/single_vs_multi_comparison.md` | `docs/single_vs_multi_comparison.md` | ✅ Hoàn thành |
| Điền `docs/system_architecture.md` | `docs/system_architecture.md` | ✅ Hoàn thành |
| Viết `reports/group_report.md` | `reports/group_report.md` | ✅ Hoàn thành |
| Chạy grading + nộp `grading_run.jsonl` | `artifacts/grading_run.jsonl` | ✅ Hoàn thành |
| Viết báo cáo cá nhân | `reports/individual/dao_hong_son.md` | ✅ Hoàn thành |

**Các functions tôi implement trong `eval_trace.py`:**
- `run_test_questions()` — chạy 15 câu test, lưu trace vào `artifacts/traces/`
- `run_grading_questions()` — chạy 10 câu grading, lưu `grading_run.jsonl`
- `analyze_traces()` — phân tích trace, tính metrics tổng hợp
- `compute_routing_accuracy()` — so khớp route thực tế vs expected
- `compare_single_vs_multi()` — so sánh Day 08 vs Day 09
- `save_eval_report()` — lưu kết quả ra JSON
- CLI entry (`if __name__ == "__main__"`)

**Bằng chứng:**
- 15 file trace trong `artifacts/traces/` có filename dạng
  `run_<timestamp>_q01.json` … `_q15.json`
- `artifacts/grading_run.jsonl` có 10 dòng — kết quả grading thực tế
- `artifacts/eval_report.json` — báo cáo tổng hợp metrics

**Cách công việc kết nối với thành viên khác:**
Tôi dùng các hàm `graph.py` (Phú) và các `workers/*` (Phú, Định, Khang), `run_graph(task)` rồi đọc `state` trả về để lưu trace và tính metric.
Contract `AgentState` mà Sprint 1 định nghĩa là interface tôi phụ thuộc hoàn toàn.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

### Quyết định: Thêm hàm `compute_routing_accuracy()` để so khớp route

**Vấn đề:** Scoring rubric (SCORING.md §2.2) yêu cầu ≥3 routing decisions
thực tế có kết quả đúng/sai. Không có hàm này tôi phải so tay 15 trace
để biết câu nào route đúng, câu nào sai.

**Các lựa chọn thay thế:**
- (a) Chỉ tính distribution (bao nhiêu câu đi vào mỗi worker) — dễ, đã có
  sẵn. Nhưng không trả lời được "route có đúng không?".
- (b) Gọi LLM judge để chấm câu trả lời cuối — đắt, chạy 15 câu tốn nhiều
  token, không cần thiết ở tầng routing.
- (c) Function riêng so khớp route vs expected_route — nhẹ, deterministic,
  output list `mismatches` dùng trực tiếp để viết `routing_decisions.md`.

**Lý do chọn (c):** Nhẹ, deterministic, không tốn token. Quan trọng hơn,
nó sinh ra bằng chứng cụ thể cho câu q02 mismatch → dẫn thẳng vào mục
"cải tiến" trong `single_vs_multi_comparison.md`.

**Trade-off đã chấp nhận:** Hàm chỉ check route layer, không chấm nội dung
answer. Cần một `accuracy_judge()` riêng cho phần đó (ngoài scope Sprint 4
của tôi).

**Bằng chứng từ trace/code:**

```python
# eval_trace.py — hàm tôi thêm
def compute_routing_accuracy(traces_dir, questions_file):
    for qid, q in questions.items():
        expected = q.get("expected_route")
        actual = traces[qid].get("supervisor_route", "")
        if actual == expected: match += 1
        else: mismatches.append({"id": qid, "expected": expected, "actual": actual})
    return {"routing_match": f"{match}/{total}", ...}
```

**Kết quả thực tế:**
- Trên 15 test questions: **14/15 (93.3%)** route đúng
- Trên 10 grading questions: **10/10 (100%)** route đúng

---

## 3. Tôi đã sửa những lỗi gì? (trong phạm vi Sprint 4)

### Lỗi 1: `analyze_traces()` crash `UnicodeDecodeError`

**Symptom:**
```
UnicodeDecodeError: 'charmap' codec can't decode byte 0x81
```
khi `json.load(f)` trên Windows.

**Root cause:** Trên Windows, `open(path)` mặc định `cp1252`, không đọc
được chuỗi tiếng Việt trong trace.

**Cách sửa:** Thêm `encoding="utf-8"` vào `open()` trong
`analyze_traces()`.

---

### Lỗi 2: 15 trace bị overwrite, chỉ còn 2 file

**Symptom:** `$ ls artifacts/traces/ | wc -l` trả về 2 thay vì 15.

**Root cause:** `graph.py::make_initial_state` đặt
`run_id = f"run_{now.strftime('%Y%m%d_%H%M%S')}"`. Khi 15 câu chạy
trong cùng 1 giây, mọi run có cùng `run_id` → cùng filename →
`save_trace` ghi đè liên tục.

**Cách sửa:** Tại `run_test_questions()`, sau khi gọi `run_graph`,
tôi append `question_id` vào `run_id`:
`result["run_id"] = f"{result['run_id']}_{q_id}"`. Không đụng `graph.py`
vì đó là territory của Phú — fix ở tầng eval là đủ.

**Bằng chứng trước/sau:**
```
# Trước
$ ls artifacts/traces/ | wc -l
2

# Sau
$ ls artifacts/traces/ | wc -l
15
```

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?** Biến trace từ "dữ liệu thô" thành
"bằng chứng có thể cite trong docs". Mọi con số trong 3 file docs/ và
group report đều có nguồn cụ thể trong `artifacts/eval_report.json`
hoặc trace file, không bịa.

**Tôi làm chưa tốt ở điểm nào?** Cần cập nhật `eval_report.json` với
số liệu grading thực tế. Hiện tại file sinh từ 15 test questions,
chưa phản ánh grading run 17:33–17:35.

**Nhóm phụ thuộc vào tôi ở đâu?** Toàn bộ deliverable bắt buộc thuộc
Sprint 4: grading run log, 3 docs, group report. Nếu `eval_trace.py`
không chạy được hay trace thiếu field, các thành viên khác không có cách
độc lập sinh log đủ format SCORING.md yêu cầu — nhóm sẽ mất điểm hạng
mục Grading (30đ) và Documentation (10đ).

**Phần tôi phụ thuộc vào thành viên khác:** Cần `AgentState` có đủ
field (`supervisor_route`, `route_reason`, `workers_called`, `mcp_tools_used`,
`hitl_triggered`, `latency_ms`) — nếu một field thiếu, trace log bị mất
column, bị trừ 20%/câu theo rubric. May mắn Phú đã define đầy đủ từ
Sprint 1.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Viết `accuracy_judge(trace, expected_answer)` dùng LLM chấm semantic
match giữa `final_answer` và `expected_answer`, output score 0/0.5/1.
Lý do: `single_vs_multi_comparison.md` dùng multi-hop accuracy 67% là
đếm tay 2/3 câu — không scale. Với judge, tôi có số liệu accuracy tự
động cho cả 15 câu, đồng thời detect được hallucination để feed vào mục
"abstain rate" trong report.
