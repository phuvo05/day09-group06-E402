# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Anh Quân  
**Vai trò trong nhóm:** Worker Owner (Sprint 2 — retrieval + synthesis)  
**Ngày nộp:** 2026-04-14

---

## 1. Tôi phụ trách phần nào?

Trong Day 09, tôi phụ trách 2 worker của Sprint 2: `workers/retrieval.py` và `workers/synthesis.py`. Trọng tâm của tôi là làm `run(state)` cho mỗi worker theo đúng contract để pipeline có thể kiểm thử độc lập và trace được đầy đủ. Ở retrieval, tôi triển khai truy xuất evidence và chuẩn hóa output `retrieved_chunks`, `retrieved_sources`, `worker_io_logs`. Ở synthesis, tôi triển khai tạo `final_answer`, `sources`, `confidence`, cơ chế abstain khi thiếu context, và bảo đảm citation khi có evidence.

Module/file tôi chịu trách nhiệm:
- File chính: `workers/retrieval.py`, `workers/synthesis.py`
- Functions tôi implement: `retrieve_dense()`, `run()` (retrieval), `synthesize()`, `run()` (synthesis).

Công việc của tôi kết nối trực tiếp với supervisor và policy worker. Supervisor route query vào retrieval/policy, sau đó synthesis tổng hợp từ `retrieved_chunks` + `policy_result`. Nếu phần của tôi chưa hoàn thành, pipeline sẽ không có câu trả lời cuối đúng format chấm điểm.

Bằng chứng kỹ thuật:
- `workers/retrieval.py` ghi `retrieved_chunks`, `retrieved_sources`, `worker_io_logs`.
- `workers/synthesis.py` ghi `final_answer`, `sources`, `confidence`, và bật `hitl_triggered` khi confidence thấp.

## 2. Tôi đã ra một quyết định kỹ thuật gì?

Quyết định chính của tôi là dùng **“dense-first, lexical-fallback”** cho retrieval thay vì phụ thuộc cứng vào vector DB.

Tôi đã cân nhắc 2 lựa chọn:
1. Chỉ dùng dense retrieval với vector DB và embedding API.
2. Chỉ dùng lexical retrieval đơn giản.

Tôi không chọn (1) vì môi trường lab có rủi ro phụ thuộc runtime (model/API/index), nếu phụ thuộc cứng thì worker crash, ảnh hưởng trace và grading. Tôi không chọn (2) vì lexical-only kém hơn khi câu hỏi khác từ vựng tài liệu. Vì vậy tôi chọn dense-first để giữ chất lượng, fallback lexical để giữ khả năng chạy ổn định.

Trade-off là khi rơi vào fallback, độ chính xác semantic giảm. Đổi lại, hệ thống không “down” và vẫn trả evidence hợp lệ.

Bằng chứng từ code/trace:

```python
# workers/retrieval.py
try:
    # query ChromaDB
    ...
except Exception as e:
    print(f"⚠️  ChromaDB query failed: {e}")
    return _lexical_fallback(query, top_k=top_k)
```

Kết quả test độc lập bằng `.venv/bin/python` cho thấy retrieval trả chunks đúng domain (`sla_p1_2026.txt`, `policy_refund_v4.txt`, `access_control_sop.txt`). Ngoài ra tôi đã index lại collection `day09_docs` (77 chunks) để dense retrieval chạy ổn định trong môi trường nhóm.

## 3. Tôi đã sửa một lỗi gì?

Lỗi tôi sửa trong synthesis là **kiểm tra citation quá lỏng**.

Symptom:
- Câu trả lời có thể chứa `[` nhưng không có citation hợp lệ kiểu `[1]`, trong khi contract yêu cầu có citation khi có evidence.

Root cause:
- Điều kiện kiểm tra ở synthesis quá rộng: `elif "[" not in answer and chunks: ...`.

Cách sửa:
- Đổi điều kiện sang regex kiểm tra citation số: `re.search(r"\[\d+\]", answer)`.
- Nếu thiếu citation số thì append `Nguồn: [1] ...`.
- Bổ sung alias `worker_io_log` bên cạnh `worker_io_logs` để tương thích checklist cũ.

Bằng chứng trước/sau:

```python
# Trước
elif "[" not in answer and chunks:

# Sau
elif not re.search(r"\[\d+\]", answer) and chunks:
```

Sau khi sửa, test bằng `.venv/bin/python` cho output luôn có `[1]` ở case có evidence và vẫn abstain đúng khi `retrieved_chunks=[]`.

## 4. Tôi tự đánh giá đóng góp của mình

Điểm tôi làm tốt nhất là cân bằng giữa đúng contract và tính vận hành thực tế: worker vẫn chạy dù thiếu dependency và vẫn xuất đúng schema để trace/debug.

Điểm tôi chưa tốt là confidence vẫn heuristic, chưa phản ánh đầy đủ độ đúng ở câu multi-hop khó.

Nhóm phụ thuộc vào tôi ở đầu ra `retrieved_chunks`, `sources`, `final_answer`, `confidence`. Nếu 2 worker này không ổn định thì supervisor route đúng cũng không tạo được kết quả cuối chấm được.

Phần tôi phụ thuộc vào thành viên khác:
- dữ liệu index/KB và tích hợp MCP để retrieval ưu tiên dense retrieval thực,
- `policy_result` đầy đủ từ policy worker để synthesis xử lý exception chính xác.

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Nếu có thêm 2 giờ, tôi sẽ làm **citation mapping nhiều nguồn tự động (`[1]`, `[2]`, `[3]`) theo từng claim** thay vì chỉ enforce citation tối thiểu ở cuối câu trả lời. Lý do là các câu multi-hop (SLA + access) cần tách nguồn theo từng ý để tăng khả năng kiểm chứng và giảm rủi ro mất điểm partial credit.
