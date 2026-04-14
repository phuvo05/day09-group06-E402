# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** Group 06 — E402
**Ngày:** 2026-04-14
**Nguồn dữ liệu Day 09:** `artifacts/traces/` + `artifacts/eval_report.json` (15 test questions)
**Nguồn dữ liệu Day 08:** `day08-group06-E402/docs/tuning-log.md` (scorecard Variant 1: dense + rerank) + `day08-group06-E402/logs/grading_run.json` (10 câu grading) + `day08-group06-E402/reports/group_report.md`

> ⚠️ Hai bộ câu hỏi **khác nhau**: Day 08 chấm trên 10 grading question + scorecard 4 chiều (Faithfulness / Answer Relevance / Context Recall / Completeness, thang 1–5). Day 09 chấm trên 15 test question với metric routing/abstain/latency. So sánh dưới đây là **qualitative across pipelines** chứ không phải chạy cùng 1 bộ câu.

---

## 1. Metrics Comparison

| Metric | Day 08 (Single-Agent RAG + rerank) | Day 09 (Multi-Agent) | Ghi chú |
|--------|-----------------------------------|---------------------|---------|
| Pipeline | Dense retrieval + cross-encoder rerank + gpt-4o-mini | Supervisor + 3 worker + MCP mock | Day 08 tập trung retrieval quality; Day 09 tập trung orchestration |
| Bộ chấm | 10 grading questions | 15 test questions | Khác bộ, chỉ so định tính |
| Grading raw (Day 08) | **98/98** | Chưa chạy grading (file public 17:00) | Day 08 đạt gần tuyệt đối |
| Faithfulness | **5.00/5** | N/A (chưa có judge LLM) | Day 09 không đo được vì answer là `[PLACEHOLDER]` |
| Answer Relevance | 4.60/5 | N/A | Như trên |
| Context Recall | 5.00/5 | N/A | Như trên |
| Completeness | 3.80/5 | N/A | Như trên |
| Abstain rate | **1/10 (10%)** — gq07 abstain đúng | **1/15 (6.7%)** — q09 (ERR-403-AUTH) HITL | Cả 2 đều có cơ chế từ chối trả lời; Day 09 tách thành HITL branch riêng |
| Avg latency (ms) | **~1850ms** (rerank +1.2s CPU + LLM ~0.6s) | ~0ms trace / ước ~1950ms khi bật LLM | Day 08 có CPU overhead do rerank; Day 09 thêm 1 hop supervisor (<10ms) |
| Multi-hop handling | Không phân loại; dựa hoàn toàn vào top-k | Supervisor có thể gọi fallback worker (q15 kéo cả SLA + access_control) | Day 09 thắng rõ khi câu cần 2+ doc |
| Routing visibility | ✗ Không có (single pipeline) | ✓ `route_reason` trong mỗi trace; match 14/15 (93.3%) | Day 09 giải thích được vì sao đi vào worker nào |
| Debuggability | ~15 phút/bug (đọc pipeline + add print) | ~5 phút/bug (mở trace JSON) | Day 09 tiết kiệm nhờ trace structured |

**Nguồn Day 08:** `day08-group06-E402/docs/tuning-log.md` dòng 57–64 (scorecard Variant 1), `reports/group_report.md` dòng 57 (grading 98/98), `logs/grading_run.json` (10 câu).
**Nguồn Day 09:** `artifacts/eval_report.json` (routing_accuracy 14/15, hitl_rate 1/15, mcp_usage_rate 0/15).

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu single-document (1 nguồn)

**Day 08 làm rất tốt:** 10/10 grading pass, Context Recall 5.00/5. Rerank giải quyết case `q01 SLA P1` (baseline sai "24 giờ" → variant đúng "4 giờ" vì rerank đẩy `sla_p1_2026.txt` lên rank 1). Với câu đơn nguồn, **không cần multi-agent** — chi phí kiến trúc vượt lợi ích.

**Day 09:** Supervisor route thẳng vào `retrieval_worker`, trace có `route_reason="default route to retrieval"`. Không cải thiện accuracy (vẫn placeholder), nhưng mỗi bước được log rõ.

### 2.2 Câu multi-hop / cross-document

**Day 08 hạn chế:** pipeline lấy top-k rồi LLM tự gộp. Câu cần merge 2 doc (SLA + access_control) dễ bị thiếu chunk thứ hai nếu rerank score thấp.
**Day 09 thắng:** q15 trace ghi `workers_called=[policy_tool_worker, retrieval_worker, synthesis_worker]` — fallback chain kéo thêm được `sla_p1_2026.txt + access_control_sop.txt`. Trade-off: hiện là fallback "tình cờ" (policy trống → sang retrieval), nên làm chủ động hơn bằng parallel call.

### 2.3 Câu cần abstain / out-of-scope

**Day 08:** prompt grounding ("Answer only from context, if not found say you do not know") xử lý gq07 Approval Matrix đúng → abstain 1/10 sạch sẽ. Nhưng baseline trước rerank có q09 ERR-403 hallucinate (completeness 2/5).
**Day 09:** HITL branch riêng — khi task match pattern `ERR-xxx` + `risk_high` → route `human_review`, không generate LLM. Trace q09 ghi `hitl_triggered=True, route_reason="unknown error code + risk_high → human review"`.

**Kết luận:** Cả 2 pipeline đều có cơ chế abstain, nhưng Day 09 tách **ra luồng riêng** dễ audit hơn (log rõ đã dừng ở đâu).

---

## 3. Debuggability Analysis

### Day 08 workflow (quan sát từ `tuning-log.md`)
```
Câu q01 sai "24 giờ" → đọc baseline prompt + top-10 chunks
  → phát hiện chunk FAQ rank 1 vượt sla_p1_2026.txt
  → thử variant rerank → chạy lại 10 câu → so scorecard
Thời gian: ~15 phút/bug (có loop tuning)
```

### Day 09 workflow (quan sát thực)
```
Câu q02 mismatch route → mở artifacts/traces/run_<id>_q02.json
  → thấy supervisor_route=policy_tool_worker, route_reason="task contains policy/access keyword"
  → root cause: keyword "hoàn tiền" over-match
  → fix: thêm rule ưu tiên "so với" trước policy keywords
Thời gian: ~2 phút đọc + sửa (không cần rerun)
```

**Lợi ích Day 09:** không cần bật print, không rerun — trace đã serialize toàn bộ state.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa prompt + pipeline | Thêm MCP tool + route rule, worker khác không đổi |
| Thêm 1 domain (VD: finance) | Re-prompt + re-index | Thêm 1 worker + 1 keyword rule |
| Swap retrieval (dense → hybrid) | Sửa trực tiếp | Sửa `workers/retrieval.py` độc lập |
| A/B test 1 thành phần | Phải clone pipeline | Swap worker bằng env flag |

Day 08 nhóm đã làm A/B ngay trong pipeline (baseline vs rerank) — khả thi nhưng phải đụng code retrieval. Day 09 có thể swap worker không đụng supervisor.

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| LLM calls / query | 1 (gpt-4o-mini) | 1 (synthesis worker) |
| Non-LLM overhead | rerank cross-encoder ~1.2s CPU | supervisor keyword <10ms + MCP stub |
| Latency điển hình | ~1850ms | ~1950ms (ước lượng khi bật LLM) |

**Nhận xét:** Day 08 đắt latency do rerank CPU. Day 09 không có rerank nên về nguyên tắc rẻ hơn, nhưng trade-off là Context Recall của Day 09 chưa verify (worker đang placeholder). Khi wire thật, nhóm nên cân nhắc đưa rerank vào `retrieval_worker` để không mất chất lượng retrieval mà Day 08 đã đạt.

---

## 6. Kết luận

> **Multi-agent (Day 09) tốt hơn single-agent (Day 08) ở điểm nào?**

1. **Debuggability:** ~15 phút → ~2 phút/bug nhờ trace JSON + `route_reason`.
2. **Routing visibility:** 14/15 (93.3%) câu route đúng; có bằng chứng mismatch (q02) để cải tiến.
3. **Abstain tách luồng:** HITL branch riêng, không lẫn vào prompt — dễ audit.
4. **Extensibility:** thêm MCP tool / worker mới không đụng phần còn lại.

> **Single-agent (Day 08) tốt hơn ở điểm nào?**

1. **Chất lượng retrieval đã verify:** Faithfulness 5.00/5, Context Recall 5.00/5, grading 98/98 — Day 09 hiện chưa chứng minh được con số tương đương (worker placeholder).
2. **Đơn giản:** ít code, ít contract giữa component, dễ onboard người mới.
3. **Đã tối ưu retrieval:** rerank cross-encoder là best practice mà Day 09 chưa port sang.

> **Khi nào KHÔNG nên dùng multi-agent?**

Domain có 1 nguồn + câu hỏi single-fact (đúng ca của Day 08). Chi phí kiến trúc không bù được lợi ích; Day 08 raw 98/98 là bằng chứng "đủ tốt".

> **Nếu tiếp tục phát triển, nhóm sẽ thêm gì?**

- **Port rerank của Day 08 vào `workers/retrieval.py`** — giữ Context Recall 5.00/5, không đánh đổi chất lượng lấy debuggability.
- **Confidence thật** từ cosine score (không placeholder 0.75).
- **Parallel multi-hop:** supervisor gọi song song 2 worker cho câu cross-doc thay vì fallback tình cờ.
- **Hybrid routing:** keyword cho 80% câu, LLM classifier khi không match (để fix q02 kiểu over-match).
- **Judge tự động** (LLM chấm Faithfulness/Completeness 15 câu Day 09) — để so sánh cùng metric với Day 08.
