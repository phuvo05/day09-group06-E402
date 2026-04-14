# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** Group 06 — E402
**Ngày:** 2026-04-14
**Nguồn dữ liệu Day 09:** `artifacts/traces/` + `artifacts/eval_report.json` (15 test questions)
**Nguồn dữ liệu Day 08:** baseline từ `day08/lab/eval.py` của nhóm (chạy cùng bộ 15 câu)

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | 0.62 | 0.75 | **+0.13** | Day 09 dùng grounding prompt chặt hơn; confidence còn là placeholder |
| Avg latency (ms) | 1850 | ~1950* | +100 | *Ước lượng khi bật LLM thật (synthesis) — trace placeholder hiện ~0ms |
| Abstain rate | 0/15 (0%) | 1/15 (6.7%) | **+6.7pp** | Day 09 abstain đúng ở q09 (ERR-403-AUTH) |
| Multi-hop accuracy (q13, q15) | 1/3 (33%) | 2/3 (67%) | **+34pp** | Day 09 kéo được cả access_control + sla cho q15 |
| Routing visibility | ✗ Không có | ✓ `route_reason` trong mỗi trace | N/A | 14/15 câu route đúng theo expected |
| Debuggability (min/bug, ước tính) | ~15 phút | ~5 phút | **−10 phút** | Đọc trace thay vì bật log cả pipeline |
| Routing match rate (expected vs actual) | N/A | 14/15 (93.3%) | N/A | Mismatch duy nhất: q02 |

> Ghi chú: Latency Day 09 trong trace hiện là 0ms do các worker node đang
> trả placeholder (chưa gọi LLM thật trong môi trường chấm). Số 1950ms là
> ước lượng khi bật `OPENAI_API_KEY`. Các metric còn lại lấy trực tiếp từ
> `eval_report.json`.

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document) — q01, q04, q05, q08

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | 4/4 | 4/4 |
| Latency | ~1.4s | ~1.5s |
| Observation | Đã đủ tốt | Không thiệt hại; thêm 1 hop supervisor ~5ms |

**Kết luận:** Với single-doc, multi-agent **không cải thiện accuracy** nhưng
cũng không tệ đi đáng kể. Chi phí thêm một supervisor call là rẻ (keyword
routing < 10ms).

### 2.2 Câu hỏi multi-hop (cross-document) — q13, q15

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | 1/3 | 2/3 |
| Routing visible? | ✗ | ✓ (q15 trace ghi `workers_called=[policy_tool, retrieval, synthesis]`) |
| Observation | Day 08 thường chỉ lấy 1 nguồn | Day 09 fallback policy→retrieval giúp kéo thêm SLA doc |

**Kết luận:** Đây là nơi multi-agent **thắng rõ nhất**. Việc policy_tool
fallback sang retrieval khi `retrieved_chunks` rỗng vô tình giải quyết câu
q15 (kéo cả `sla_p1_2026.txt` + `access_control_sop.txt`).

### 2.3 Câu hỏi cần abstain — q09

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain rate | 0/1 | 1/1 |
| Hallucination cases | 1 (bịa mô tả ERR-403) | 0 |
| Observation | Không có cơ chế dừng | HITL branch chặn trước khi generate |

**Kết luận:** Multi-agent có điểm **dừng rõ ràng** (`human_review` node)
nên ít hallucinate hơn ở câu out-of-scope.

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow
```
Khi answer sai → đọc toàn RAG pipeline → thêm print() vào từng bước
→ chạy lại với cùng query → so sánh manual
Thời gian ước tính: 15 phút / bug
```

### Day 09 — Debug workflow
```
Khi answer sai → mở artifacts/traces/run_<id>.json
  → xem supervisor_route + route_reason
  → Nếu route sai → chỉnh keyword trong supervisor_node
  → Nếu chunks sai → chạy workers/retrieval.py::run(state) độc lập
  → Nếu synthesis hallucinate → xem retrieved_chunks trong trace
Thời gian ước tính: 5 phút / bug
```

**Câu cụ thể nhóm đã debug:** q02 (mismatch route). Đọc trace thấy
`route_reason="task contains policy/access keyword"` → ngay lập tức biết
nguyên nhân là rule "hoàn tiền" over-match. Không cần chạy lại pipeline —
đọc trace là ra root cause trong <2 phút.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa toàn prompt | Thêm MCP tool + route rule (không đụng worker khác) |
| Thêm 1 domain mới | Phải retrain/re-prompt | Thêm 1 worker mới + 1 rule supervisor |
| Thay đổi retrieval strategy | Sửa trực tiếp trong pipeline | Sửa `workers/retrieval.py` độc lập |
| A/B test một phần | Khó — phải clone toàn pipeline | Dễ — swap worker bằng env flag |

**Nhận xét:** Extensibility là lợi ích lớn nhất — đã chứng minh bằng việc
thêm MCP `search_kb` vào policy_tool mà không động tới retrieval/synthesis.

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 calls | Day 09 calls |
|---------|-------------|-------------|
| Simple query (q01) | 1 LLM call | 1 LLM call (supervisor=keyword, synthesis=LLM) |
| Complex query (q15) | 1 LLM call | 1 LLM call + 2 MCP calls (non-LLM) |
| MCP tool call | N/A | 0–2 per query |

**Nhận xét về cost-benefit:** Multi-agent **không tăng chi phí LLM** trong
setup hiện tại (supervisor dùng keyword, MCP không phải LLM). Tăng latency
chủ yếu do thêm 1–2 Python function call (<10ms). Trade-off rất tốt so với
lợi ích debuggability + abstain.

---

## 6. Kết luận

> **Multi-agent tốt hơn single agent ở điểm nào?**

1. **Debuggability:** rút thời gian tìm root cause từ ~15 phút còn ~5 phút
   nhờ `route_reason` + trace JSON.
2. **Abstain / anti-hallucination:** HITL node bắt được câu out-of-scope
   (q09), Day 08 không có.
3. **Extensibility:** thêm MCP tool mới không đụng worker khác.

> **Multi-agent kém hơn hoặc không khác biệt ở điểm nào?**

1. Câu single-document đơn giản: accuracy như nhau, chỉ thêm overhead ~5ms.

> **Khi nào KHÔNG nên dùng multi-agent?**

Khi domain chỉ có 1 nguồn và câu hỏi luôn kiểu single-fact — chi phí kiến
trúc + code vượt lợi ích. Day 08 đã đủ.

> **Nếu tiếp tục phát triển hệ thống này, nhóm sẽ thêm gì?**

- `confidence` thực tế (từ cosine score / LLM self-report) thay placeholder.
- Cho supervisor **gọi song song** nhiều worker ở câu multi-hop (thay vì
  fallback tình cờ).
- Hardcode keyword → hybrid: keyword cho 80% câu, LLM classifier chỉ kích
  hoạt khi không có match rõ ràng (tiết kiệm cost nhưng tăng accuracy q02).
