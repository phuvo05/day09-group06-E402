# TASKS — Lab Day 09 · Group 06

## Thành viên

| # | Họ tên | MSSV |
|---|--------|------|
| 1 | Nguyễn Anh Quân | 2A202600132 |
| 2 | Võ Thiên Phú | 2A202600336 |
| 3 | Phan Dương Định | 2A202600277 |
| 4 | Phạm Minh Khang | 2A202600417 |
| 5 | Đào Hồng Sơn | 2A202600462 |

---

## Phân công

### Nguyễn Anh Quân — Supervisor Owner (Sprint 1)

- [ ] Implement `AgentState` trong `graph.py`
- [ ] Implement `supervisor_node()` — đọc task, quyết định route
- [ ] Implement `route_decision()` — routing logic theo keyword
- [ ] Kết nối graph: `supervisor → route → workers → synthesis → END`
- [ ] Chạy `graph.invoke()` với ≥2 test queries, log `route_reason`
- [ ] Viết báo cáo cá nhân: `reports/individual/nguyen_anh_quan.md`

**Deadline code:** 18:00

---

### Võ Thiên Phú — Worker Owner (Sprint 2 — retrieval + synthesis)

- [ ] Implement `workers/retrieval.py` — `run(state)`, ghi `retrieved_chunks` + `worker_io_log`
- [ ] Implement `workers/synthesis.py` — `run(state)`, gọi LLM, output có `answer`, `sources`, `confidence`
- [ ] Test từng worker độc lập (không cần graph)
- [ ] Đảm bảo synthesis trả về citation `[1]`, không hallucinate
- [ ] Viết báo cáo cá nhân: `reports/individual/vo_thien_phu.md`

**Deadline code:** 18:00

---

### Phan Dương Định — Worker Owner (Sprint 2 — policy) + Contracts

- [ ] Implement `workers/policy_tool.py` — `run(state)`, xử lý exception case (Flash Sale / digital product)
- [ ] Điền/cập nhật `contracts/worker_contracts.yaml` cho cả 3 workers
- [ ] Test `policy_tool.py` độc lập với ít nhất 1 exception case
- [ ] Viết báo cáo cá nhân: `reports/individual/phan_duong_dinh.md`

**Deadline code:** 18:00

---

### Phạm Minh Khang — MCP Owner (Sprint 3)

- [ ] Implement `mcp_server.py` với ≥2 tools: `search_kb()` và `get_ticket_info()`
- [ ] Tích hợp MCP client vào `workers/policy_tool.py` (thay direct ChromaDB call)
- [ ] Đảm bảo trace ghi `mcp_tool_called` và `mcp_result` cho mỗi lần gọi
- [ ] Viết báo cáo cá nhân: `reports/individual/pham_minh_khang.md`

**Deadline code:** 18:00

---

### Đào Hồng Sơn — Trace & Docs Owner (Sprint 4)

- [ ] Implement `eval_trace.py` — chạy 15 test questions, lưu trace vào `artifacts/traces/`
- [ ] Implement `analyze_trace()` và `compare_single_vs_multi()`
- [ ] Điền `docs/routing_decisions.md` — ≥3 quyết định routing thực tế từ trace
- [ ] Điền `docs/single_vs_multi_comparison.md` — ≥2 metrics có số liệu
- [ ] Điền `docs/system_architecture.md` — sơ đồ pipeline + lý do chọn supervisor-worker
- [ ] Viết `reports/group_report.md`
- [ ] Chạy pipeline với `grading_questions.json` (17:00–18:00), nộp `artifacts/grading_run.jsonl`
- [ ] Viết báo cáo cá nhân: `reports/individual/dao_hong_son.md`

**Deadline code + grading log:** 18:00  
**Deadline reports:** sau 18:00 được phép

---

## Lịch sprint

| Sprint | Thời gian | Người lead |
|--------|-----------|-----------|
| Sprint 1 — Refactor Graph | 60' đầu | Nguyễn Anh Quân |
| Sprint 2 — Build Workers | 60' tiếp | Võ Thiên Phú + Phan Dương Định |
| Sprint 3 — MCP | 60' tiếp | Phạm Minh Khang |
| Sprint 4 — Trace & Docs | 60' cuối | Đào Hồng Sơn |

---

## Checklist nộp bài (18:00)

- [ ] `graph.py` chạy được, route ≥2 loại task
- [ ] `workers/retrieval.py`, `workers/policy_tool.py`, `workers/synthesis.py` test độc lập được
- [ ] `mcp_server.py` có ≥2 tools, được gọi từ worker
- [ ] `contracts/worker_contracts.yaml` đầy đủ
- [ ] `eval_trace.py` chạy end-to-end 15 câu
- [ ] `artifacts/traces/` có trace files
- [ ] `artifacts/grading_run.jsonl` (chạy sau 17:00)
- [ ] `docs/system_architecture.md`, `docs/routing_decisions.md`, `docs/single_vs_multi_comparison.md`
- [ ] `reports/group_report.md`
- [ ] `reports/individual/` — 5 file cá nhân
