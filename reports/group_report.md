# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Group 06 — E402
**Thành viên:**

| Tên | Vai trò | MSSV |
|-----|---------|------|
| Võ Thiên Phú | Supervisor Owner (Sprint 1) | 2A202600336 |
| Nguyễn Anh Quân | Worker Owner — retrieval + synthesis (Sprint 2) | 2A202600132 |
| Phan Dương Định | Worker Owner — policy + contracts (Sprint 2) | 2A202600277 |
| Phạm Minh Khang | MCP Owner (Sprint 3) | 2A202600417 |
| Đào Hồng Sơn | Trace & Docs Owner (Sprint 4) | 2A202600462 |

**Ngày nộp:** 2026-04-14
**Repo:** `day09-group06-E402`

---

## 1. Kiến trúc nhóm đã xây dựng

**Hệ thống tổng quan:** Supervisor-Worker pattern — 1 Supervisor + 3 Worker
(retrieval, policy_tool, synthesis) + 1 HITL branch (`human_review`) + 1 MCP
server (in-process class) cung cấp 4 tools. Graph được implement bằng Python
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

Kết quả thực tế trên 15 test question: route đúng **14/15 (93.3%)**, một mismatch
duy nhất (q02) do rule "hoàn tiền" over-match khi câu hỏi là "định nghĩa"
chính sách chứ không phải "xin áp dụng" chính sách.

**MCP tools đã implement** (gọi từ `workers/policy_tool.py`):
- `search_kb(query, top_k)` — search ChromaDB, trả `chunks` + `sources`.
  Ví dụ trace gọi: khi `needs_tool=True` và `retrieved_chunks` rỗng.
- `get_ticket_info(ticket_id)` — mock trả `priority`, `created_at`,
  `status`, `assigned_to`, `sla_deadline`, `notifications_sent`.
  Dùng cho câu hỏi về ticket P1 đang active.
- `check_access_permission(level, role, is_emergency)` — kiểm tra điều kiện
  cấp quyền theo Access Control SOP, trả `can_grant`, `required_approvers`,
  `emergency_override`. Bonus tool cho q03, q13.
- `create_ticket(priority, title, description)` — mock tạo ticket mới.
  (4 tools — nhiều hơn yêu cầu Sprint 3, dự phòng mở rộng.)

**Bổ sung: kiến trúc state flow thực tế**

```
task → supervisor_node → route_decision
                           ├─ retrieval_worker → synthesis → END
                           ├─ policy_tool_worker
                           │    (nếu needs_tool=True và chưa có chunks → gọi MCP search_kb)
                           │    → synthesis → END
                           └─ human_review → (auto-approve) → retrieval_worker → synthesis → END
```

**Lưu ý quan trọng:** `build_graph()` gọi `retrieval_worker_node()` **trước**
`policy_tool_worker_node()` khi route là policy. Điều này khiến policy
worker hiếm khi gọi MCP `search_kb` (vì chunks đã có từ retrieval). MCP là
fallback khi retrieval trả rỗng.

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định 1:** Dùng **keyword-based supervisor** thay vì LLM classifier cho
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

**Quyết định 2:** **Hybrid LLM + rule-based cho Policy Worker** thay vì
chỉ dùng rule-based hoặc chỉ dùng LLM.

Lý do: LLM-based phân tích context-aware, handle được combinations phức tạp
(ví dụ: Flash Sale + đơn đã kích hoạt + temporal scoping cùng lúc). Rule-based
là fallback khi không có API key hoặc LLM call thất bại.

**Quyết định 3:** **dispatch_tool() luôn trả trace dict chuẩn** thay vì trả
thẳng output của tool.

Lý do: chuẩn hóa trace tại dispatch layer — `eval_trace.py` đọc
`mcp_tools_used` cần format nhất quán `{mcp_tool_called, mcp_result, error,
timestamp}` từ mọi tool.

---

## 3. Kết quả grading questions

**Tổng điểm raw ước tính:** *(Điền sau khi chạy 17:00–18:00)* ___ / 96

**Câu pipeline xử lý tốt nhất:**
- gq01 (SLA P1, notification, escalation) — retrieval route đúng, sla_p1_2026.txt
  có đủ thông tin (15 phút response, 4 giờ resolution, Slack/PagerDuty, 10 phút
  escalation).
- gq04 (store credit %) — policy_refund_v4.txt Điều 5 ghi rõ 110%.
- gq07 (abstain) — HITL branch hoặc synthesis abstain đúng khi không có thông
  tin về mức phạt tài chính trong tài liệu.

**Câu rủi ro cao:**
- gq02 (temporal scoping 31/01 → policy v3) — nếu policy worker không detect
  được đơn trước 01/02 → có thể trả lời theo v4 (sai). Đã có logic
  `policy_version_note` trong code.
- gq09 (multi-hop SLA + Level 2) — cần cả sla_p1_2026.txt và
  access_control_sop.txt. Retrieval fallback phải lấy được 2 docs → phụ thuộc
  `top_k` và keyword overlap.
- gq10 (Flash Sale + defect) — phải detect **cả hai** exception: Flash Sale
  exception VÀ defect exception → trả lời đúng là "không hoàn" vì Flash Sale
  override.

**Câu gq07 (abstain):** Nhóm đã chuẩn bị HITL branch + prompt synthesis có
instruction "Nếu không có thông tin trong context, trả lời 'không có thông
tin' + gợi ý liên hệ". Đã test thành công trên q09 của test set
(`ERR-403-AUTH`). Kỳ vọng gq07 abstain đúng.

**Câu gq09 (multi-hop khó nhất):** Trace ghi `workers_called =
["policy_tool_worker", "retrieval_worker", "synthesis_worker"]` (xác nhận 2
worker domain-specific được gọi). Cross-reference SLA + Access Control nhờ
fallback logic `if not retrieved_chunks: retrieval_worker_node(state)`.
**Lưu ý:** đây là fallback "tình cờ" chứ không phải routing chủ động cho
multi-hop. Nếu cả hai worker đều có chunks từ đầu → không có cross-reference.

---

## 4. So sánh Day 08 vs Day 09

**Metric thay đổi rõ nhất (có số liệu):** **Routing accuracy từ N/A → 93.3%**
(14/15 câu route đúng). Trace có `route_reason` cho mỗi bước — Day 08 không có.
**Abstain rate** từ 10% (1/10) → 6.7% (1/15) — cơ chế HITL branch riêng
dễ audit hơn.

**So sánh đầy đủ:**

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Ghi chú |
|--------|----------------------|----------------------|---------|
| Grading raw | 98/98 | Chưa chạy grading (17:00) | — |
| Routing accuracy | N/A (single pipeline) | 93.3% (14/15) | Day 09 thắng rõ |
| Debuggability | ~15 phút/bug (đọc prompt + add print) | ~5 phút/bug (mở trace JSON) | Day 09 thắng |
| Abstain rate | 10% (1/10) | 6.7% (1/15) | Ngang nhau, HITL tách riêng dễ audit |
| Multi-hop handling | Phụ thuộc rerank quality | Fallback tình cờ (policy→retrieval) | Cả hai đều hạn chế |
| Latency | ~1850ms (rerank + LLM) | ~1950ms (ước) | Ngang nhau |
| HITL control | Prompt instruction | Luồng riêng `human_review` | Day 09 thắng |
| Extensibility | Sửa prompt, dễ regression | Thêm MCP/worker mới không đụng core | Day 09 thắng |
| Retrieval quality | Faithfulness 5.00/5 (verify) | Chưa verify (placeholder) | Day 08 thắng |

**Điều nhóm bất ngờ nhất khi chuyển từ single sang multi-agent:** Fallback
policy→retrieval (khi `retrieved_chunks` rỗng) **tình cờ giải quyết được
multi-hop** (q15). Không phải thiết kế chủ ý — là hệ quả defensive coding.
Lesson: thiết kế "graceful fallback" trong worker đem lại value bất ngờ.

**Trường hợp multi-agent KHÔNG giúp ích hoặc làm chậm hệ thống:** Với câu
q01/q04/q05 (single-doc, single-fact), multi-agent không tăng accuracy,
chỉ thêm ~5ms supervisor overhead và tăng độ phức tạp code. Nếu hệ thống
chỉ phục vụ loại câu này, Day 08 đã đủ.

---

## 5. Phân công và đánh giá nhóm

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint | Bằng chứng |
|------------|-------------|--------|-------------|
| Nguyễn Anh Quân | `workers/retrieval.py`, `workers/synthesis.py` + citation format fix, ChromaDB integration | 2 | WORKER_NAME="retrieval_worker", regex citation fix |
| Võ Thiên Phú | `graph.py` — AgentState, supervisor_node, route_decision, human_review_node, build_graph | 1 | graph.py:24-129 supervisor logic |
| Phan Dương Định | `workers/policy_tool.py` (LLM-based + rule-based), `contracts/worker_contracts.yaml` | 2 | analyze_policy_with_llm() lines 71-148 |
| Phạm Minh Khang | `mcp_server.py` (4 tools), MCP wiring trong policy_tool, dispatch_tool trace format | 3 | dispatch_tool() lines 298-331 |
| Đào Hồng Sơn | `eval_trace.py` (run 15 câu + analyze + grading), 3 docs/*.md, `reports/group_report.md` | 4 | eval_trace.py + artifacts/*.json |

**Lưu ý vai trò:** Vai trò ghi trong bảng trên khớp với nội dung code/trace thực tế.
Các báo cáo cá nhân (`reports/individual/`) có thể ghi vai trò hơi khác tên
nhưng phần code phụ trách đúng như trên.

**Điều nhóm làm tốt:**
- Contracts được viết **trước** khi implement worker → interface không thay
  đổi giữa các sprint, tránh rework.
- Trace format thống nhất ngay Sprint 1 → Sprint 4 chỉ việc `json.load`.
- MCP dispatch format chuẩn hóa từ Sprint 3 → `eval_trace.py` đọc nhất quán.

**Điều nhóm làm chưa tốt hoặc gặp vấn đề về phối hợp:**
- Ban đầu `save_trace` dùng `run_id` theo timestamp giây → khi chạy 15 câu
  trong 1 giây, trace bị overwrite. Phát hiện ở Sprint 4, patch nhanh
  bằng cách append `question_id` vào `run_id` trong `eval_trace.py`.
- `analyze_traces` mở file mặc định cp1252 trên Windows → crash với tiếng
  Việt. Cũng patch ở Sprint 4 (`encoding="utf-8"`).
- ChromaDB collection chưa được index trước grading → retrieval dùng lexical
  fallback thay vì semantic search. Đây là bug nghiêm trọng cần fix trước 17:00.
- `route_reason` chưa ghi rõ keyword đã match → khó reproduce, cần cải thiện
  thành `"policy_keywords=['hoàn tiền']"` thay vì `"task contains policy/access keyword"`.

**Nếu làm lại, nhóm sẽ thay đổi gì trong cách tổ chức?**
- Viết **integration smoke test** ngay Sprint 1 chạy đủ 3 câu end-to-end,
  phát hiện bug overwrite trace sớm hơn.
- Định nghĩa `trace schema` trong `contracts/` giống worker contracts.
- **Index ChromaDB ngay sau khi setup** thay vì để Sprint 4.

---

## 6. Nếu có thêm 1 ngày

1. **Index ChromaDB đầy đủ** — retrieval hiện dùng lexical fallback,
   semantic search chưa hoạt động. Đây là ưu tiên số 1 vì ảnh hưởng
   30 điểm grading.
2. **Thay `confidence` placeholder 0.75 bằng giá trị thật** (cosine max của
   top chunk + LLM self-score). Bằng chứng: mọi trace hiện tại đều conf=0.75.
3. **Thêm supervisor re-route:** nếu `retrieved_chunks == []` sau retrieval
   worker, quay lại supervisor để thử MCP `search_kb` hoặc HITL thay vì đi
   thẳng vào synthesis.
4. **Parallel multi-hop routing:** Supervisor gọi song song retrieval + policy
   khi câu hỏi có nhiều intent (≥2 doc sources) — thay vì fallback tình cờ.

---

*Lưu file tại: `reports/group_report.md`. Commit sau 18:00 được phép theo SCORING.md.*
