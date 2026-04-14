# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Phạm Minh Khang  
**MSSV:** 2A202600417  
**Vai trò trong nhóm:** MCP Owner (Sprint 3)  
**Ngày nộp:** 2026-04-14

---

## 1. Tôi phụ trách phần nào?

Tôi phụ trách Sprint 3 — MCP (Model Context Protocol) integration.

**Module/file tôi chịu trách nhiệm:**
- File chính: `mcp_server.py`, `workers/policy_tool.py`
- Functions tôi implement/sửa:
  - `dispatch_tool()` trong `mcp_server.py` — thêm trace `mcp_tool_called` và `mcp_result` vào mọi lần gọi tool
  - `_call_mcp_tool()` trong `workers/policy_tool.py` — refactor để dùng trực tiếp `dispatch_tool()` thay vì wrap lại với key khác
  - Phần `run()` trong `policy_tool.py` — sửa để đọc đúng key `mcp_result` thay vì `output`

**Cách công việc của tôi kết nối với phần của thành viên khác:**

`mcp_server.py` cung cấp `dispatch_tool()` cho `workers/policy_tool.py` (Phan Dương Định). Trace `mcp_tools_used` trong state được `eval_trace.py` (Đào Hồng Sơn) đọc để phân tích. `search_kb` trong MCP server gọi lại `workers/retrieval.py` (Võ Thiên Phú) để query ChromaDB.

**Bằng chứng:** File `mcp_server.py` và `workers/policy_tool.py` có comment Sprint 3, các key `mcp_tool_called`/`mcp_result` được thêm trong lab hôm nay.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Thay đổi return format của `dispatch_tool()` để luôn trả về dict có key chuẩn `mcp_tool_called` và `mcp_result`, thay vì trả thẳng output của tool.

**Các lựa chọn thay thế:**
- Option A (cũ): `dispatch_tool()` trả thẳng output của tool (e.g., `{"chunks": [...], "sources": [...]}`)
- Option B (tôi chọn): `dispatch_tool()` luôn trả `{"mcp_tool_called": "search_kb", "mcp_result": {...}, "error": None, "timestamp": "..."}`

**Lý do chọn Option B:**

Với Option A, caller phải tự biết tool nào trả về key gì để log trace — dẫn đến code lặp ở mỗi nơi gọi. Option B chuẩn hóa trace ngay tại dispatch layer: bất kỳ caller nào cũng có thể append kết quả vào `mcp_tools_used` mà không cần xử lý thêm. Điều này quan trọng vì `eval_trace.py` cần đọc `mcp_tool_called` và `mcp_result` từ mọi entry trong `mcp_tools_used`.

**Trade-off đã chấp nhận:** Caller phải đọc `result["mcp_result"]` thay vì `result` trực tiếp — thêm một level nesting. Nhưng đổi lại trace luôn nhất quán.

**Bằng chứng từ code:**

```python
# mcp_server.py — dispatch_tool() sau khi sửa
trace = {
    "mcp_tool_called": tool_name,
    "mcp_input": tool_input,
    "mcp_result": None,
    "error": None,
    "timestamp": datetime.now().isoformat(),
}
# ...
trace["mcp_result"] = tool_fn(**tool_input)
return trace

# workers/policy_tool.py — đọc đúng key
kb_result = mcp_result.get("mcp_result") or {}
if kb_result.get("chunks"):
    chunks = kb_result["chunks"]
```

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** `policy_tool.py` không đọc được chunks từ MCP response sau khi `dispatch_tool()` đổi format.

**Symptom:** Khi `needs_tool=True` và `retrieved_chunks=[]`, worker gọi `search_kb` qua MCP nhưng `chunks` vẫn rỗng — pipeline tiếp tục với context trống, `policy_result` không chính xác.

**Root cause:** Code cũ dùng `mcp_result.get("output")` để lấy kết quả tool:

```python
# Cũ — sai key
if mcp_result.get("output") and mcp_result["output"].get("chunks"):
    chunks = mcp_result["output"]["chunks"]
```

Nhưng sau khi `dispatch_tool()` đổi sang trả `mcp_result` thay vì `output`, key `"output"` không còn tồn tại → `chunks` luôn rỗng.

**Cách sửa:** Đổi sang đọc đúng key `mcp_result`:

```python
# Mới — đúng key
kb_result = mcp_result.get("mcp_result") or {}
if kb_result.get("chunks"):
    chunks = kb_result["chunks"]
```

**Bằng chứng trước/sau:**

Trước: `policy_result = {"policy_applies": True, "exceptions_found": [], ...}` dù task là Flash Sale (vì không có chunks để detect exception).

Sau: `policy_result = {"policy_applies": False, "exceptions_found": [{"type": "flash_sale_exception", ...}], ...}` — đúng.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?**

Chuẩn hóa trace format tại dispatch layer — quyết định này giúp cả `policy_tool.py` và `eval_trace.py` không cần xử lý riêng từng tool. Mọi MCP call đều có `mcp_tool_called` và `mcp_result` nhất quán.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

`search_kb` trong MCP server hiện vẫn gọi lại `workers/retrieval.py` trực tiếp (in-process), chưa phải HTTP MCP server thật. Nếu retrieval worker chưa setup ChromaDB, `search_kb` fallback về mock data — trace có `mcp_result` nhưng data không thật.

**Nhóm phụ thuộc vào tôi ở đâu?**

`workers/policy_tool.py` phụ thuộc vào `dispatch_tool()` để gọi `search_kb` khi không có chunks. `eval_trace.py` phụ thuộc vào format `mcp_tool_called`/`mcp_result` trong `mcp_tools_used` để phân tích MCP usage.

**Phần tôi phụ thuộc vào thành viên khác:**

Tôi phụ thuộc vào Võ Thiên Phú (`workers/retrieval.py`) — cụ thể là function `retrieve_dense()` mà `tool_search_kb()` gọi. Nếu ChromaDB chưa được ingest data, `search_kb` sẽ trả mock data.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement HTTP MCP server thật bằng FastAPI để `dispatch_tool()` gọi qua HTTP thay vì in-process import. Lý do: trace hiện tại của các câu policy (e.g., gq05 Flash Sale) cho thấy `mcp_tool_called=search_kb` nhưng latency gần 0ms — chứng tỏ đang gọi in-process, không phải network call thật. HTTP server sẽ cho phép đo latency MCP thực tế và test isolation giữa server và client.
