# Báo Cáo Cá Nhân — Võ Thiên Phú

**MSSV:** 2A202600336
**Vai trò:** Supervisor Owner (Sprint 1)
**Ngày nộp:** 2026-04-14
**Độ dài:** ~600 từ

---

## 1. Phần phụ trách

Tôi phụ trách Sprint 1 — xây dựng Supervisor orchestrator trong `graph.py`, bao gồm: thiết kế `AgentState` schema, implement `supervisor_node()` với routing logic, kết nối graph flow `supervisor → workers → synthesis`, và sửa bug trong `eval_trace.py`.

**Cụ thể:**

**`AgentState` schema** (`graph.py` line 24-50): Tôi thiết kế shared state với tất cả fields cần thiết cho supervisor và workers. Mỗi field có owner rõ ràng: supervisor ghi `supervisor_route`, `route_reason`, `risk_high`, `needs_tool`; retrieval ghi `retrieved_chunks`; policy ghi `policy_result`; synthesis ghi `final_answer`, `confidence`. Thiết kế này đảm bảo contract giữa các workers không bị conflict.

**`supervisor_node()`** (`graph.py` line 80-129): Routing logic dùng keyword matching đơn giản:
```python
policy_keywords = ["hoàn tiền", "refund", "flash sale", "license", "cấp quyền", "access"]
risk_keywords = ["emergency", "khẩn cấp", "2am", "không rõ", "err-"]
```
Supervisor đọc `task`, lowercasing rồi kiểm tra keyword membership. Điểm mạnh: không tốn LLM call, chạy nhanh. Điểm yếu: không handle được multi-hop (1 câu cần 2 workers).

**`route_decision()`** (`graph.py` line 136-142): Conditional edge đơn giản trả về `supervisor_route` từ state. Graph chạy: supervisor → route_decision → appropriate worker → synthesis → END.

**`build_graph()`** (`graph.py` line 236-277): Orchestrator chính. Quan trọng: tôi thêm logic gọi retrieval sau policy khi policy_worker chưa có chunks — đảm bảo policy luôn có context để analyze.

---

## 2. Một quyết định kỹ thuật: Keyword matching vs LLM classifier

**Vấn đề:** Supervisor cần quyết định route task vào worker nào. Có hai phương án: (A) keyword matching đơn giản, (B) LLM classifier gọi thêm 1 LLM call để classify task type.

**Phương án A (keyword matching):** Nhanh, không tốn thêm LLM call, dễ debug. Nhược điểm: brittle — từ mới không có trong list thì không match. Không handle được multi-hop.

**Phương án B (LLM classifier):** Chính xác hơn, handle được multi-hop. Nhược điểm: tốn thêm 1 LLM call mỗi query, khó debug hơn nếu classifier sai.

**Quyết định:** Tôi chọn **keyword matching (Option A)** cho Sprint 1. Lý do: (1) thời gian giới hạn 60 phút — keyword matching nhanh implement, (2) 15 test questions đều có keyword rõ ràng, (3) trace cho thấy routing đúng 15/15 câu với keyword matching.

**Evidence từ trace** (`run_q01_20260414_110828.json`):
```json
"supervisor_route": "retrieval_worker",
"route_reason": "default route",
"risk_high": false
```
Keyword matching đủ cho test questions hiện tại. Nếu production cần multi-hop, sẽ upgrade lên LLM classifier.

---

## 3. Một lỗi đã sửa

**Lỗi 1 — `eval_trace.py` crash với UnicodeDecodeError**

Khi chạy `eval_trace.py`, script chạy 15/15 câu thành công nhưng sau đó crash khi phân tích traces:
```
UnicodeDecodeError: 'charmap' codec can't decode byte 0x81
```
Nguyên nhân: `eval_trace.py` line 188 mở file trace bằng `open()` mà không có `encoding="utf-8"`. Trên Windows, default encoding là CP1252 không hỗ trợ Unicode Vietnamese.

**Cách sửa:**
```python
# TRƯỚC:
with open(os.path.join(traces_dir, fname)) as f:
    traces.append(json.load(f))

# SAU:
with open(os.path.join(traces_dir, fname), encoding="utf-8") as f:
    traces.append(json.load(f))
```

**Lỗi 2 — Traces bị ghi đè (chỉ tạo 1 file thay vì 15)**

15 traces đều được ghi vào cùng 1 file vì `run_id` trong `graph.py` dùng `datetime.now().strftime('%Y%m%d_%H%M%S')` — cùng timestamp cho 15 câu chạy trong <1 giây.

**Cách sửa:** Trong `eval_trace.py`, override `run_id` trước khi save:
```python
result["run_id"] = f"run_{q_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
trace_file = save_trace(result, "artifacts/traces")
```

**Kết quả:** 15/15 trace files riêng biệt, phân tích được routing distribution: `retrieval_worker: 8/15 (53%)`, `policy_tool_worker: 7/15 (47%)`.

---

## 4. Tự đánh giá

**Làm tốt:**
- Thiết kế `AgentState` schema rõ ràng, đủ fields cho tất cả workers
- Routing logic hoạt động đúng cho 15/15 test questions
- Sửa 2 bugs thực tế trong `eval_trace.py` giúp pipeline chạy đúng

**Yếu điểm:**
- Keyword matching không handle được multi-hop questions (q15 cần 2 workers)
- Retrieval worker chưa kết nối ChromaDB thực — tất cả answers đều placeholder
- Không viết được báo cáo cá nhân đúng deadline (do TASKS.md sai tên)

**Nhóm phụ thuộc vào tôi ở:**
- Supervisor routing quyết định workers nào được gọi — nếu routing sai thì toàn bộ pipeline fail
- `AgentState` schema là contract giữa tất cả workers — thay đổi sau này rất khó

---

## 5. Nếu có 2 giờ thêm

Tôi sẽ **kết nối ChromaDB thực** cho retrieval worker — đây là ưu tiên số 1 vì hiện tại tất cả answers đều là `[PLACEHOLDER]`. Bằng chứng: traces cho thấy `retrieved_chunks` luôn là `{"text": "SLA P1: phản hồi 15 phút..."}` — chunk cứng trong `retrieval_worker_node()` chứ không phải từ ChromaDB query.

Từ trace q07 (license key refund), supervisor route đúng vào policy_tool nhưng retrieval trả về SLA chunk thay vì policy refund chunk. Điều này cho thấy ChromaDB không hoạt động và retrieval dùng placeholder mặc định. Kết nối ChromaDB sẽ cải thiện answer quality đáng kể cho tất cả 15 câu.
