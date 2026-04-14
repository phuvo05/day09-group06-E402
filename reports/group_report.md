# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Group 06 — E402
**Thành viên:**

| Tên | Vai trò | MSSV |
|-----|---------|------|
| Nguyễn Anh Quân | Supervisor Owner (Sprint 1) | 2A202600132 |
| Võ Thiên Phú | Worker Owner — retrieval + synthesis (Sprint 2) | 2A202600336 |
| Phan Dương Định | Worker Owner — policy + contracts (Sprint 2) | 2A202600277 |
| Phạm Minh Khang | MCP Owner (Sprint 3) | 2A202600417 |
| Đào Hồng Sơn | Trace & Docs Owner (Sprint 4) | 2A202600462 |

**Ngày nộp:** 2026-04-14
**Repo:** `day09-group06-E402`

---

## 1. Kiến trúc nhóm đã xây dựng

**Hệ thống tổng quan:** Supervisor-Worker pattern — 1 Supervisor + 3 Worker
(retrieval, policy_tool, synthesis) + 1 HITL branch (`human_review`) + 1 MCP
server (in-process class) cung cấp 2 tools. Graph được implement bằng Python
thuần trong `graph.py::build_graph` (không dùng LangGraph để giảm dependency).
State chia sẻ là `AgentState` — một `TypedDict` với ~15 field (xem
`docs/system_architecture.md` §4).

**Routing logic cốt lõi:** Supervisor dùng **keyword matching** trên task đã
lower-cased.
- `hoàn tiền / refund / flash sale / license / cấp quyền / access / level 3`
  → `policy_tool_worker`.
- `emergency / khẩn cấp / 2am / err-` → `risk_high = True`.
- `risk_high AND err-` → `human_review` (sau đó auto-approve + retrieval).
- Còn lại → `retrieval_worker` (default).

Kết quả thực tế trên 15 test question: route đúng 14/15 (93.3%), một mismatch
duy nhất (q02) do rule "hoàn tiền" over-match.

**MCP tools đã tích hợp** (gọi từ `workers/policy_tool.py`):
- `search_kb(query, top_k)` — search ChromaDB, trả `chunks` + `sources`.
  Ví dụ trace gọi: q07 `search_kb("license key refund policy", top_k=3)`.
- `get_ticket_info(ticket_id)` — mock trả `priority`, `created_at`,
  `status`, `assigned_to`. Dùng cho q11, q15 (ticket 2am).
- `check_access_permission(level, role)` — bonus tool cho access control
  questions (q03, q13).

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định:** Dùng **keyword-based supervisor** thay vì LLM classifier cho
routing.

**Bối cảnh vấn đề:** Supervisor cần route sang 1 trong 3 worker. Option 1:
gọi LLM với prompt "phân loại câu hỏi". Option 2: rule-based keyword.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| LLM classifier (gpt-4o-mini) | Hiểu intent tinh tế, xử lý được câu q02 | +800ms latency, +1 LLM call/query (tăng cost), khó reproduce |
| Keyword matching | <10ms, deterministic, dễ debug, không tốn token | Over-match ở câu biên (q02), khó phủ hết synonyms |
| Hybrid (keyword → LLM khi không match) | Cân bằng | Phức tạp, chưa có thời gian implement đúng |

**Phương án đã chọn và lý do:** Keyword matching. Lý do:
1. Với 5 domain rõ ràng (SLA / Refund / Access / HR / IT Helpdesk),
   keyword phủ ~93% case — đủ tốt cho MVP.
2. Tiết kiệm được 800ms × 15 câu = 12s/grading run, giảm cost LLM call.
3. `route_reason` có thể in thẳng rule matched — debug không cần rerun.
4. Trade-off đã chấp nhận: q02 route sai, giải quyết được bằng rule tinh
   chỉnh, không cần đổi kiến trúc.

**Bằng chứng từ trace/code:**

```python
# graph.py::supervisor_node
policy_keywords = ["hoàn tiền", "refund", "flash sale", "license",
                   "cấp quyền", "access", "level 3"]
if any(kw in task for kw in policy_keywords):
    route = "policy_tool_worker"
    route_reason = "task contains policy/access keyword"
```

```json
// artifacts/traces/run_<id>_q07.json (trích)
"supervisor_route": "policy_tool_worker",
"route_reason": "task contains policy/access keyword",
"latency_ms": 0    // Supervisor <5ms, tổng pipeline chi phối bởi synthesis
```

---

## 3. Kết quả grading questions

**Tổng điểm raw ước tính:** *(Điền sau khi chạy 17:00–18:00)* ___ / 96

**Câu pipeline xử lý tốt nhất:**
- q01 / q03 / q04 — retrieval single-doc, route đúng, cite nguồn chính xác.
- Lý do: keyword routing + retrieval ChromaDB đủ cho câu single-fact.

**Câu pipeline fail hoặc partial:** *(điền sau khi chạy grading)*
- ID: ___ — Fail ở đâu: ___
  Root cause: ___

**Câu gq07 (abstain):** Nhóm đã chuẩn bị HITL branch + prompt synthesis có
instruction "Nếu không có thông tin trong context, trả lời 'không có thông
tin' + gợi ý liên hệ". Đã test thành công trên q09 của test set
(`ERR-403-AUTH`). Kỳ vọng gq07 abstain đúng.

**Câu gq09 (multi-hop khó nhất):** Trace ghi `workers_called =
["policy_tool_worker", "retrieval_worker", "synthesis_worker"]` (xác nhận 2
worker domain-specific được gọi). Cross-reference SLA + Access Control nhờ
fallback logic `if not retrieved_chunks: retrieval_worker_node(state)`.

---

## 4. So sánh Day 08 vs Day 09

**Metric thay đổi rõ nhất (có số liệu):** **Multi-hop accuracy từ 33% → 67%**
(1/3 → 2/3). Route_reason + HITL visibility từ **✗ → ✓** — chỉ Day 09 mới có
`route_reason` trong trace.

**Điều nhóm bất ngờ nhất khi chuyển từ single sang multi-agent:** Fallback
policy→retrieval (khi `retrieved_chunks` rỗng) **tình cờ giải quyết được
multi-hop** (q15). Không phải thiết kế chủ ý — là hệ quả defensive coding.
Lesson: thiết kế "graceful fallback" trong worker đem lại value bất ngờ.

**Trường hợp multi-agent KHÔNG giúp ích hoặc làm chậm hệ thống:** Với câu
q01/q04/q05 (single-doc, single-fact), multi-agent không tăng accuracy,
chỉ thêm ~5ms supervisor overhead. Nếu hệ thống chỉ phục vụ loại câu này,
Day 08 đã đủ.

---

## 5. Phân công và đánh giá nhóm

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Nguyễn Anh Quân | `graph.py` — AgentState, supervisor_node, route_decision, human_review_node, build_graph | 1 |
| Võ Thiên Phú | `workers/retrieval.py`, `workers/synthesis.py` + citation format | 2 |
| Phan Dương Định | `workers/policy_tool.py` + `contracts/worker_contracts.yaml` + exception cases | 2 |
| Phạm Minh Khang | `mcp_server.py` (2+1 tools) + MCP client wiring trong policy_tool | 3 |
| Đào Hồng Sơn | `eval_trace.py` (chạy 15 câu + analyze + compare + grading run), 3 docs/*.md, `reports/group_report.md` | 4 |

**Điều nhóm làm tốt:**
- Contracts được viết **trước** khi implement worker → interface không thay
  đổi giữa các sprint, tránh rework.
- Trace format thống nhất ngay Sprint 1 → Sprint 4 chỉ việc `json.load`.

**Điều nhóm làm chưa tốt hoặc gặp vấn đề về phối hợp:**
- Ban đầu `save_trace` dùng `run_id` theo timestamp giây → khi chạy 15 câu
  trong 1 giây, trace bị overwrite. Phát hiện ở Sprint 4, patch nhanh
  bằng cách append `question_id` vào `run_id` trong `eval_trace.py`.
- `analyze_traces` mở file mặc định cp1252 trên Windows → crash với tiếng
  Việt. Cũng patch ở Sprint 4 (`encoding="utf-8"`).

**Nếu làm lại, nhóm sẽ thay đổi gì trong cách tổ chức?**
- Viết **integration smoke test** ngay Sprint 1 chạy đủ 3 câu end-to-end,
  phát hiện bug overwrite trace sớm hơn.
- Định nghĩa `trace schema` trong `contracts/` giống worker contracts.

---

## 6. Nếu có thêm 1 ngày

1. **Thay `confidence` placeholder 0.75 bằng giá trị thật** (cosine max của
   top chunk + LLM self-score). Bằng chứng cần cải tiến: mọi trace hiện tại
   đều conf=0.75 → metric `avg_confidence` mất ý nghĩa.
2. **Thêm supervisor re-route:** nếu `retrieved_chunks == []` sau retrieval
   worker, quay lại supervisor để thử MCP `search_kb` hoặc HITL thay vì đi
   thẳng vào synthesis (hiện đang dẫn tới abstain đúng nhưng không chủ ý).

---

*File này lưu tại: `reports/group_report.md`. Commit sau 18:00 được phép theo SCORING.md.*
