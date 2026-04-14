# Routing Decisions Log — Lab Day 09

**Nhóm:** Group 06 — E402
**Ngày:** 2026-04-14
**Nguồn dữ liệu:** `artifacts/traces/` (15 trace files từ `test_questions.json`)

---

## Routing Decision #1 — q01 (retrieval, single-doc)

**Task đầu vào:**
> SLA xử lý ticket P1 là bao lâu?

**Worker được chọn:** `retrieval_worker`
**Route reason (từ trace):** `default route` (không match policy keyword, không match risk keyword)
**MCP tools được gọi:** —
**Workers called sequence:** `retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): Trả lời SLA P1 = 15 phút phản hồi, 4 giờ xử lý, cite `sla_p1_2026.txt`
- confidence: 0.75
- Correct routing? **Yes** (khớp `expected_route=retrieval_worker`)

**Nhận xét:** Đây là "happy path" — câu single-doc, retrieval trả chunk đúng,
synthesis cite 1 nguồn. Route reason hơi thô ("default route"), đáng cải thiện
thành "no policy/risk keyword → retrieval".

---

## Routing Decision #2 — q07 (policy, exception case)

**Task đầu vào:**
> Sản phẩm kỹ thuật số (license key) có được hoàn tiền không?

**Worker được chọn:** `policy_tool_worker`
**Route reason (từ trace):** `task contains policy/access keyword` (match "hoàn tiền", "license")
**MCP tools được gọi:** `search_kb` (query="license key refund policy")
**Workers called sequence:** `policy_tool_worker → retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): Không hoàn — sản phẩm kỹ thuật số thuộc exception Điều 3
- confidence: 0.75
- Correct routing? **Yes** (khớp expected `policy_tool_worker`)

**Nhận xét:** Route đúng và policy worker phát hiện đúng exception "digital
product". Đây là case chứng minh lợi ích tách policy_tool_worker — Day 08
single agent thường "quên" check exception và trả refund-allowed.

---

## Routing Decision #3 — q09 (HITL, abstain)

**Task đầu vào:**
> ERR-403-AUTH là lỗi gì và cách xử lý?

**Worker được chọn (lần 1):** `human_review`
**Route reason (từ trace):** `unknown error code + risk_high → human review`
**MCP tools được gọi:** —
**Workers called sequence:** `human_review → retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: abstain — "Không có thông tin về ERR-403-AUTH, đề nghị liên hệ IT Helpdesk"
- confidence: 0.75 (thực tế nên thấp hơn — xem section "cải tiến")
- `hitl_triggered: true`
- Correct routing? **Yes** — đúng ý đồ: mã lỗi lạ → flag rủi ro → HITL trước khi trả lời

**Nhận xét:** Là case duy nhất trigger HITL trong 15 câu (6.7%). Nhờ HITL
branch, pipeline không hallucinate một mô tả ERR-403 bịa. Route reason ở đây
rất có giá trị debug — nhìn vào là biết ngay vì sao route.

---

## Routing Decision #4 — q15 (multi-hop, bonus — khó nhất)

**Task đầu vào:**
> Ticket P1 lúc 2am. Cần cấp Level 2 access tạm thời cho contractor để thực hiện emergency fix. Đồng thời cần notify stakeholders theo SLA. Nêu đủ cả hai quy trình.

**Worker được chọn:** `policy_tool_worker`
**Route reason:** `task contains policy/access keyword | risk_high flagged` (match "access" + "2am"/"emergency")

**Nhận xét: Đây là trường hợp routing khó nhất trong lab. Tại sao?**

- Câu yêu cầu **hai nguồn** song song: `sla_p1_2026.txt` (notification) và
  `access_control_sop.txt` (Level 2 emergency bypass).
- Rule keyword hiện tại chỉ chọn được 1 route chính. Nhưng vì policy_tool
  luôn fallback sang retrieval khi `retrieved_chunks` rỗng, cuối cùng cả hai
  file đều được lấy. Đây là may mắn của design, không phải routing logic dự
  tính.
- Bài học: với multi-hop, một rule-based supervisor không đủ — cần (a) cho
  phép supervisor gọi **nhiều** worker, hoặc (b) để synthesis tự yêu cầu thêm
  retrieval khi câu hỏi có nhiều intent.

---

## Tổng kết

### Routing Distribution (từ `analyze_traces()` trên 15 trace)

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 8 | 53.3% |
| policy_tool_worker | 7 | 46.7% |
| human_review (entry) | 1 | 6.7% (q09 trigger HITL, sau đó đi retrieval) |

### Routing Accuracy (`compute_routing_accuracy()`)

- Câu route đúng theo `expected_route`: **14 / 15** (93.3%)
- Câu route sai: **1 / 15** — q02 "Khách hàng có thể yêu cầu hoàn tiền trong
  bao nhiêu ngày?" → expected `retrieval_worker` nhưng thực tế
  `policy_tool_worker` do rule match "hoàn tiền".
  - **Sửa đề xuất:** tách "câu hỏi định nghĩa" vs "câu hỏi áp dụng chính
    sách" — thêm rule: nếu task bắt đầu bằng "bao nhiêu"/"bao lâu"/"gì" và
    không có tình huống cụ thể → retrieval, kể cả khi có keyword policy.
- Câu trigger HITL: **1 / 15** (q09 — mã lỗi không xác định)

### Lesson Learned về Routing

1. **Keyword routing 93% đủ dùng cho 5 categories**, không cần LLM classifier.
   Trade-off: tiết kiệm ~800ms/call nhưng mất khả năng hiểu intent tinh tế
   (q02 là ví dụ).
2. **`route_reason` phải có dạng `<rule matched> | <flags>`** — format hiện
   tại đủ để debug nhanh, nhưng nên append keyword thực sự match (ví dụ
   `match=['hoàn tiền']`) để không phải chạy lại pipeline khi debug.

### Route Reason Quality

Các `route_reason` hiện tại như `"task contains policy/access keyword"`
đủ biết route nhưng **không đủ reproduce** — không thấy keyword nào đã match.
Cải tiến Sprint 4 đã định (nếu có thêm thời gian): đổi thành
`"policy keyword matched: ['flash sale', 'hoàn tiền']"` để debug không cần
rerun pipeline.
