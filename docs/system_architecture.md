# System Architecture — Lab Day 09

**Nhóm:** Group 06 — E402
**Ngày:** 2026-04-14
**Version:** 1.0

---

## 1. Tổng quan kiến trúc

Hệ thống Day 09 là phiên bản refactor của RAG pipeline Day 08 sang
pattern **Supervisor-Worker**: một Supervisor đọc task, quyết định worker nào
cần gọi; các Worker thực hiện một nhiệm vụ chuyên biệt (retrieval, policy
check, synthesis) và chia sẻ dữ liệu qua một `AgentState` duy nhất. Một MCP
server cung cấp hai tool (`search_kb`, `get_ticket_info`) để Policy Worker gọi
external capability thay vì hard-code.

**Pattern đã chọn:** Supervisor-Worker (implement Option A — Python thuần, xem
`graph.py::build_graph`).

**Lý do chọn pattern này (thay vì single agent):**

- Day 08 là một hàm `rag_answer()` monolith — khi pipeline trả lời sai, không
  biết lỗi nằm ở indexing, retrieval, hay generation.
- Tách Supervisor + 3 Worker giúp **test độc lập từng bước** (evidence: mỗi
  file `workers/*.py` có `run(state)` chạy được mà không cần graph).
- Trace ghi `route_reason`, `workers_called`, `mcp_tools_used` — debug bằng
  cách đọc trace thay vì đọc lại prompt.

---

## 2. Sơ đồ Pipeline

```
                          User Question
                               │
                               ▼
                      ┌────────────────┐
                      │  Supervisor    │   route_reason, risk_high, needs_tool
                      │  (graph.py)    │
                      └───────┬────────┘
                              │
                     [route_decision]
          ┌───────────────────┼────────────────────┐
          │                   │                    │
          ▼                   ▼                    ▼
   retrieval_worker    policy_tool_worker    human_review
   ChromaDB search     ├─ MCP: search_kb     (risk_high +
   top-k chunks        ├─ MCP: get_ticket    ERR-xxx code)
                       └─ exception check          │
          │                   │                    │ auto-approve
          │                   │ (fallback:         ▼
          │                   │  retrieval nếu     retrieval_worker
          │                   │  chưa có chunks)
          └───────────┬───────┴────────────────────┘
                      ▼
              ┌──────────────────┐
              │ Synthesis Worker │   grounded LLM call,
              │  answer + cite   │   confidence score,
              └────────┬─────────┘   abstain-if-empty
                       ▼
                   Final Output
                       │
                       ▼
              artifacts/traces/*.json   (trace đầy đủ + route_reason)
```

---

## 3. Vai trò từng thành phần

### Supervisor (`graph.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Đọc `task`, phân loại, ghi `supervisor_route`, `route_reason`, `risk_high`, `needs_tool` vào state |
| **Input** | `state.task` (string) |
| **Output** | `supervisor_route`, `route_reason`, `risk_high`, `needs_tool` |
| **Routing logic** | Keyword matching: nhóm *policy* (hoàn tiền/refund/flash sale/license/cấp quyền/access/level 3) → `policy_tool_worker`; nhóm *risk* (emergency/khẩn cấp/2am/err-) → `risk_high=True`; risk_high + `err-` → `human_review`; còn lại → `retrieval_worker` |
| **HITL condition** | `risk_high=True` AND task chứa mã lỗi không xác định (`err-`) |

### Retrieval Worker (`workers/retrieval.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Query ChromaDB, trả về top-k chunks + source filenames |
| **Embedding model** | `all-MiniLM-L6-v2` (kế thừa từ Day 08) |
| **Top-k** | 4 |
| **Stateless?** | Yes — chỉ đọc `state.task`, ghi `retrieved_chunks`, `retrieved_sources`, `worker_io_log` |

### Policy Tool Worker (`workers/policy_tool.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Kiểm tra policy applies/exceptions; gọi MCP tools để tra KB và ticket info |
| **MCP tools gọi** | `search_kb(query, top_k)`, `get_ticket_info(ticket_id)` |
| **Exception cases xử lý** | Flash Sale (refund 50% hoặc voucher), digital product (license key → không hoàn), temporal scoping (đơn trước effective date) |

### Synthesis Worker (`workers/synthesis.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **LLM model** | `gpt-4o-mini` (fallback sang placeholder khi thiếu API key) |
| **Temperature** | 0.1 |
| **Grounding strategy** | Prompt "Answer ONLY from the provided context" + citations `[1]`, `[2]`; abstain nếu không có evidence |
| **Abstain condition** | `retrieved_chunks == []` hoặc không chunk nào match keyword câu hỏi |

### MCP Server (`mcp_server.py`)

| Tool | Input | Output |
|------|-------|--------|
| `search_kb` | `query: str`, `top_k: int` | `chunks: list`, `sources: list` |
| `get_ticket_info` | `ticket_id: str` | `priority`, `created_at`, `status`, `assigned_to` |
| `check_access_permission` | `access_level`, `requester_role` | `can_grant`, `approvers` (bonus tool) |

---

## 4. Shared State Schema

| Field | Type | Mô tả | Ai đọc/ghi |
|-------|------|-------|-----------|
| `task` | str | Câu hỏi đầu vào | supervisor đọc |
| `supervisor_route` | str | Worker được chọn | supervisor ghi, route_decision đọc |
| `route_reason` | str | Lý do route (human-readable) | supervisor ghi, trace đọc |
| `risk_high` | bool | Có flag rủi ro không | supervisor ghi |
| `needs_tool` | bool | Có cần MCP tool không | supervisor ghi, policy đọc |
| `retrieved_chunks` | list | Evidence từ retrieval | retrieval ghi, synthesis đọc |
| `retrieved_sources` | list | Tên file nguồn | retrieval ghi, synthesis đọc |
| `policy_result` | dict | Kết quả kiểm tra policy | policy_tool ghi, synthesis đọc |
| `mcp_tools_used` | list | Tool calls đã thực hiện | policy_tool ghi, trace đọc |
| `workers_called` | list | Sequence worker đã chạy | mỗi worker append |
| `hitl_triggered` | bool | Đã pause cho human chưa | human_review ghi |
| `final_answer` | str | Câu trả lời cuối | synthesis ghi |
| `confidence` | float | Độ tin cậy (0–1) | synthesis ghi |
| `latency_ms` | int | Thời gian xử lý | graph ghi khi kết thúc |
| `run_id` | str | ID unique cho trace file | graph ghi |

---

## 5. Lý do chọn Supervisor-Worker so với Single Agent (Day 08)

| Tiêu chí | Single Agent (Day 08) | Supervisor-Worker (Day 09) |
|----------|----------------------|--------------------------|
| Debug khi sai | Khó — phải đọc toàn prompt + code | Đọc `route_reason`, test từng worker độc lập |
| Thêm capability mới | Sửa toàn prompt, dễ regression | Thêm MCP tool + route rule, không đụng worker khác |
| Routing visibility | Không có | `route_reason` có trong mọi trace |
| Kiểm soát HITL | Không có điểm pause rõ | `human_review` node rõ ràng, toggle bằng flag |
| Chi phí LLM call | 1 call/query | 1–2 call/query (synthesis + optional classifier) |

**Quan sát từ thực tế lab:**

- Trên 15 test questions, supervisor route đúng 14/15 (93.3%) chỉ bằng keyword
  rule — không cần LLM classifier (trade-off chi phí/độ chính xác).
- Câu q09 (`ERR-403-AUTH`) là câu duy nhất trigger HITL; nhờ đó pipeline
  không hallucinate mã lỗi bịa, giữ được abstain behavior.
- Case mismatch duy nhất (q02 "hoàn tiền") cho thấy rule `contains("hoàn tiền")`
  đang over-match: đáng lẽ là retrieval đơn giản nhưng bị route policy.

---

## 6. Giới hạn và điểm cần cải tiến

1. **Keyword routing thô** — chưa phân biệt được câu "hỏi định nghĩa chính
   sách" (retrieval) và "xin áp dụng chính sách" (policy_tool). Đã thấy ở q02.
2. **Confidence placeholder** — synthesis đang trả hard-code 0.75; cần tính
   dựa trên cosine score hoặc LLM self-report để trace có ý nghĩa.
3. **MCP mock** — `mcp_server.py` là class trong process, chưa tách HTTP;
   không test được failure/timeout thật của tool call.
4. **HITL auto-approve** — `human_review_node` in cảnh báo rồi tự route tiếp;
   trong production cần block thật và chờ approval.
5. **Không có re-route** — nếu retrieval trả chunks rỗng, pipeline vẫn đi
   thẳng vào synthesis thay vì quay lại supervisor để thử policy_tool hoặc
   HITL.
