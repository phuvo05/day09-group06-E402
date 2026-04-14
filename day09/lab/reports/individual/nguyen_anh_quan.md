# Báo cáo cá nhân — Nguyễn Anh Quân (2A202600132)

## 1) Phần tôi phụ trách

Trong Day 09, tôi phụ trách Sprint 2 với vai trò Worker Owner cho 2 module:
- `workers/retrieval.py`
- `workers/synthesis.py`

Mục tiêu tôi xử lý là tách rõ 2 trách nhiệm:
- Retrieval chỉ lo lấy evidence từ KB.
- Synthesis chỉ tổng hợp câu trả lời dựa trên evidence đã có, không tự bịa.

## 2) Những gì tôi đã implement

### 2.1 Retrieval Worker (`workers/retrieval.py`)

- Implement `run(state)` theo contract:
  - Input: `task`, `top_k`/`retrieval_top_k`
  - Output: `retrieved_chunks`, `retrieved_sources`, `worker_io_logs`
- Kết nối ChromaDB collection `day09_docs`, query theo embedding.
- Chuẩn hóa `score` về khoảng `[0.0, 1.0]`.
- Bổ sung fallback lexical retrieval trên `data/docs` để worker vẫn test độc lập được khi chưa có index/model.
- Ghi trace:
  - `worker_io_logs` (mảng theo contract)
  - `worker_io_log` (bản ghi gần nhất để thuận tiện debug)

### 2.2 Synthesis Worker (`workers/synthesis.py`)

- Implement `run(state)` để tổng hợp từ:
  - `task`
  - `retrieved_chunks`
  - `policy_result`
- Output đầy đủ:
  - `answer` (theo checklist Sprint 2)
  - `final_answer` (tương thích graph hiện tại)
  - `sources`
  - `confidence`
- Grounding guardrails:
  - Nếu `retrieved_chunks=[]` thì abstain: `"Không đủ thông tin trong tài liệu nội bộ..."`.
  - Không có evidence thì không gọi LLM để tránh hallucination.
- Citation guardrails:
  - Ép output có citation dạng `[1]` nếu LLM chưa tự chèn.
- Confidence:
  - Tính từ độ liên quan chunk + penalty exception.
  - Nếu `< 0.4` thì bật `hitl_triggered=True`.
- Ghi `worker_io_logs` + `worker_io_log`.

## 3) Test độc lập đã chạy

Tôi chạy test trực tiếp từng worker bằng entrypoint trong file:
- `python workers/retrieval.py`
- `python workers/synthesis.py`

Kết quả mong đợi sau test:
- Retrieval trả được cấu trúc chunks/sources đúng schema.
- Synthesis trả `answer/final_answer/sources/confidence`.
- Khi thiếu evidence, synthesis trả lời abstain thay vì tự suy diễn.
- Khi có evidence, output có citation `[1]`.

## 4) Một lỗi tôi đã xử lý

Lỗi quan trọng ban đầu:
- Synthesis có thể trả lời dù không có retrieved chunks, dễ gây hallucination.

Cách tôi sửa:
- Chặn sớm trong `synthesize()`:
  - Nếu không có chunks thì trả lời abstain cố định.
  - Confidence hạ thấp (`0.2`) và không gọi LLM.

Tác động:
- Đáp ứng ràng buộc contract: "`retrieved_chunks=[]` phải abstain".
- Giảm nguy cơ answer sai khi retrieval thất bại.

## 5) Tự đánh giá

Điểm làm tốt:
- Worker IO bám contract, dễ trace.
- Có fallback để test local ổn định.
- Bổ sung guardrail chống hallucination và bảo đảm citation.

Điểm cần cải thiện:
- Citation hiện mới ở mức format (`[1]`), chưa có post-check map chi tiết từng câu với chunk id.
- Confidence vẫn heuristic, chưa dùng LLM-as-judge.

Nếu có thêm thời gian, tôi sẽ:
1. Thêm bộ test tự động (pytest) cho các case no-evidence / exception / multi-source.
2. Chuẩn hóa format citation theo `[source_name]` + `[1]` song song.
3. Bổ sung quality gate kiểm tra answer chỉ chứa fact xuất hiện trong chunks.
