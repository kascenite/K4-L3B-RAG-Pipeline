# Individual contribution report

## Thông tin

- Họ và tên: ______
- Mã học viên: ______
- Nhóm: làm cá nhân (solo) — đề tài: pháp luật cho hộ kinh doanh
- Repository/branch: ______ / `main`

## Phần việc đã thực hiện

| Module/deliverable | Việc tôi trực tiếp làm | File/commit/PR | Trạng thái |
|---|---|---|---|
| Thu thập dữ liệu (Task 1–2) | 5 văn bản pháp luật (NĐ 168/2025, NĐ 68/2026, NĐ 141/2026, NĐ 254/2026, TT 18/2026) từ Công báo/Cổng Chính phủ; 8 bài báo có `url`, `title`, `date_crawled` | `src/task1_collect_legal_docs.py`, `src/task2_crawl_news.py`, `data/landing/` | Done |
| Chuẩn hoá Markdown (Task 3) | Convert PDF/DOCX/JSON sang Markdown có header title/source | `src/task3_convert_markdown.py`, `data/standardized/` | Done |
| Chunk + index (Task 4) | Recursive chunk 1000/150 cắt theo Chương/Điều; `gemini-embedding-2` 768 chiều; ChromaDB cosine; cache embedding để index lại không tốn quota và không trùng dữ liệu (529 chunk); ghi chú sửa đổi NĐ 141 cho chunk NĐ 68 | `src/task4_chunking_indexing.py` | Done |
| Dense, BM25, RRF (Task 5–7) | Dense search dùng chung `embed_texts`; BM25Plus tách token theo âm tiết; RRF k=60, không mutate input | `src/task5_semantic_search.py`, `src/task6_lexical_search.py`, `src/task7_reranking.py` | Done |
| Fallback + pipeline (Task 8–9) | Hiệu chỉnh threshold 0.68 theo dense cosine; PageIndex có cache doc ID, timeout, lỗi không làm dừng pipeline | `src/task8_pageindex_vectorless.py`, `src/task9_retrieval_pipeline.py` | Partial — PageIndex chưa chạy thật vì chưa có API key |
| Generation + UI (Task 10) | Citation `[n]` map đúng `sources[n-1]` dù context đã reorder; safe refusal; Streamlit hiển thị answer, nguồn, method, score | `src/task10_generation.py`, `app.py` | Done |
| Evaluation | 15 câu golden bám corpus; ragas 4 metric; A/B dense-only vs hybrid + RRF; phân tích lỗi | `src/evaluate.py`, `group_project/evaluation/` | Done |

## Quyết định kỹ thuật quan trọng

1. **Quyết định:** Dùng hybrid (dense + BM25) + RRF làm retrieval mặc định.  
   **Lý do/evidence:** Trên 15 câu golden, context recall tăng từ 0.833 lên 0.933 và context precision từ 0.763 lên 0.795. BM25 bắt được cụm từ chính xác mà dense bỏ sót, ví dụ câu "nhiều cửa hàng… mã số thuế" có recall 0.0 ở dense-only và 1.0 ở hybrid.  
   **Trade-off:** Không tốn thêm lời gọi API (BM25 chạy local), nhưng phải giữ corpus BM25 đồng bộ với ChromaDB.

2. **Quyết định:** Gắn ghi chú sửa đổi vào chunk của văn bản gốc thay vì chỉ sửa prompt.  
   **Lý do/evidence:** NĐ 141/2026 sửa NĐ 68/2026 bằng cách thay cụm từ, nên chunk gốc ghi "500 triệu đồng" luôn đứng top 1. Khi chỉ thêm quy tắc vào prompt, chatbot vẫn trả lời 500 triệu trong 4/4 lần. Sau khi gắn ghi chú, chatbot trả lời đúng mức 01 tỷ.  
   **Trade-off:** Bảng `AMENDMENTS` phải cập nhật thủ công mỗi khi có văn bản sửa đổi mới.

## Kiểm thử và kết quả

- Test hoặc query tôi đã dùng:
  - `pytest -q`: 20/20 pass.
  - Hiệu chỉnh threshold bằng 6 query in-domain (cosine 0.75–0.83) và 6 query out-of-domain (0.52–0.61).
  - Demo in-domain: "thông báo tài khoản ngân hàng… chậm nhất khi nào?" trả lời 20/4/2026 [1][2].
  - Demo out-of-domain: "Công thức nấu phở bò Hà Nội?" trả về safe refusal, không crash.
- Kết quả trước/sau nếu có:
  - Điểm trung bình 4 metric: dense-only 0.843, hybrid + RRF 0.903.
  - Câu hỏi ngưỡng thuế: trước khi sửa trả lời 500 triệu (sai), sau khi sửa trả lời 01 tỷ (đúng).
- Lỗi đã phát hiện và cách xử lý:
  - Ngưỡng thuế trả lời theo mức đã bị thay: gắn ghi chú sửa đổi vào chunk và thêm quy tắc prompt.
  - Lỗi provider (quota, 500/503) trước đây bị ghi thành câu từ chối: tách `raise_errors` trong eval và thêm retry có backoff.
  - Free tier chỉ cho `gemini-3.5-flash` 20 request/ngày: chuyển generator sang `gemma-4-26b-a4b-it`.

## Điều còn hạn chế

- Một hạn chế cụ thể của phần tôi làm: PageIndex fallback chưa được chạy với API thật. Điểm A/B được đo trước khi sửa lỗi ngưỡng thuế và chưa chấm lại.
- Nếu có thêm thời gian, thay đổi đầu tiên tôi sẽ thực hiện: chấm lại A/B bằng judge mạnh hơn (chấm nhiều lần rồi lấy trung bình) và thêm reranker sau RRF để tăng context precision.

## Xác nhận đóng góp

Tôi xác nhận nội dung trên phản ánh đúng phần việc của mình và có thể giải thích hoặc chạy lại trong buổi demo.

- Ngày: ______
- Tên thành viên: ______
