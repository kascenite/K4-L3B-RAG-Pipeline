# RAG evaluation results

Đề tài: hỏi đáp pháp luật cho hộ kinh doanh (đăng ký, thuế, hóa đơn điện tử 2025–2026).

## Run information

| Field                              | Value |
| ---------------------------------- | ----- |
| Evaluation date                    | 2026-09-25 |
| Framework and version              | ragas 0.4.3 (`ragas.metrics.collections`), script `src/evaluate.py` |
| Evaluator model                    | `gemini-3.5-flash-lite` (Gemini API, endpoint OpenAI-compatible); embedding cho answer relevancy: `gemini-embedding-2`. Lượt chấm đầu dùng `max_tokens` mặc định 1024; ô faithfulness câu 8 của A bị cắt output nên được chấm lại với `max_tokens=4096` (mặc định hiện tại của `src/evaluate.py`). |
| Generator model                    | `gemma-4-26b-a4b-it` (Gemini API), temperature 0.3, top_p 0.9 |
| Embedding model                    | `gemini-embedding-2`, 768 chiều, cosine (ChromaDB) |
| Corpus version/commit              | 5 văn bản pháp luật + 8 bài báo, 529 chunks (1000 ký tự, overlap 150); base commit `a23df34` + thay đổi chưa commit |
| Golden dataset size                | 15 câu (`golden_dataset.json`), mỗi câu có `expected_answer`, `expected_context` trích nguyên văn và `source` |
| `top_k`                            | 5 (dense và BM25 mỗi bên lấy 10 ứng viên trước khi fuse) |
| Fallback threshold and calibration | `SCORE_THRESHOLD=0.68` so với cosine top-1 của dense. 6 query in-domain: 0.75–0.83; 6 query out-of-domain (phở, bóng đá, Python, thời tiết, luật hôn nhân, giá vàng): 0.52–0.61. Chọn 0.68 ở giữa hai cụm. Hai query đại diện: "Hộ kinh doanh có bắt buộc dùng hóa đơn điện tử không?" (0.811, không fallback) và "Công thức nấu phở bò Hà Nội?" (0.560, thử fallback; PageIndex không có key nên dùng hybrid và LLM từ chối). Không query golden nào kích hoạt fallback. Ngưỡng này chỉ đúng cho corpus và embedding hiện tại; đổi corpus hoặc model thì phải hiệu chỉnh lại. |

## Configurations

- **Config A — dense-only:** `retrieve(query, top_k=5, use_reranking=False)`, tức top-5 theo cosine từ ChromaDB.
- **Config B — hybrid + RRF:** `retrieve(query, top_k=5, use_reranking=True)`, gồm dense top-10 và BM25Plus top-10 (tách token theo âm tiết), fuse bằng RRF (k=60) và lấy top-5.

Hai config dùng cùng golden dataset, generator, evaluator, prompt và `top_k`; chỉ khác retrieval strategy. Câu trả lời và context được lưu trong `runs/A_dense.json` và `runs/B_hybrid_rrf.json`; điểm tổng hợp nằm trong `runs/summary.json`.

## Overall scores

| Metric            | Config A | Config B | Delta B−A |
| ----------------- | -------: | -------: | --------: |
| Faithfulness      |    0.844 |    0.967 |    +0.122 |
| Answer relevance  |    0.931 |    0.916 |    −0.015 |
| Context recall    |    0.833 |    0.933 |    +0.100 |
| Context precision |    0.763 |    0.795 |    +0.032 |
| **Average**       |    0.843 |    0.903 |    +0.060 |

## A/B comparison

- Cấu hình tốt hơn: **Config B (hybrid + RRF)**.
- Evidence:
  - Context recall tăng 0.10. BM25 bắt đúng các chunk chứa cụm từ chính xác mà dense bỏ sót.
    - Câu 4 ("nhiều cửa hàng… mã số thuế"): recall A 0.0, B 1.0. BM25 khớp cụm "mã địa điểm kinh doanh".
    - Câu 2 (hiệu lực NĐ 141): recall A 0.5, B 1.0.
  - Faithfulness tăng 0.12, nhưng **gần như toàn bộ là nhiễu của judge**, không phải lợi thế của B.
    - Câu 2 và câu 15 ở A có câu trả lời đúng, đầy đủ, có citation và giống hệt B nhưng bị chấm 0.0; B được 1.0.
    - Nếu bỏ hai câu này, faithfulness là A 0.974 và B 0.962 (B câu 3 chỉ được 0.5).
    - Vì vậy kết luận "B tốt hơn" dựa vào context recall/precision, không dựa vào faithfulness.
  - Answer relevance giảm nhẹ 0.015, nằm trong mức nhiễu vì judge chỉ sinh 1 câu hỏi ngược (strictness=1).
- Trade-off về latency/cost:
  - Retrieval: A 0.96 s/query, B 0.81 s/query. BM25 chạy local trên 529 chunks nên chi phí không đáng kể; thời gian chủ yếu là gọi API embedding query.
  - End-to-end: A 13.3 s, B 18.0 s trung bình. Hầu hết thời gian là lời gọi generator (A và B chạy tuần tự trên free tier, có backoff khi gặp 429/500/503). Không đo riêng số lần retry nên không tách được phần chênh lệch do RRF; RRF chỉ là phép tính local trên ≤20 phần tử.
  - Hybrid không tốn thêm lời gọi API nào.

## Worst performers

|   # | Question | Config | Faithfulness | Relevance | Recall | Precision | Failure stage | Root cause |
| --: | -------- | ------ | -----------: | --------: | -----: | --------: | ------------- | ---------- |
|   1 | Hộ kinh doanh có doanh thu năm bao nhiêu thì không phải nộp thuế GTGT và TNCN? | A và B | 0.67 / 1.00 | 0.91 | 0.00 | 0.25 / 0.00 | generation (xung đột nguồn) | Cả hai config trả lời **500 triệu đồng**, là mức đã bị NĐ 141/2026 thay bằng 01 tỷ. Mức 01 tỷ **có trong context** (A: chunk 2 và 4 từ bài báo về NĐ 141; B: chunk 3), nhưng chunk gốc của NĐ 68 (Điều 3–4, ghi 500 triệu) khớp câu hỏi gần như nguyên văn và đứng top 1, nên generator chọn con số này. A còn diễn giải sai rằng 01 tỷ "sẽ được nâng lên" từ 1/1/2026, như thể chưa áp dụng. Chunk sửa đổi trong chính NĐ 141 ("sửa '500 triệu đồng' thành '01 tỷ đồng'…") không được retrieve vì không nhắc tới thuế GTGT/TNCN. Recall = 0 vì reference trích từ NĐ 141. |
|   2 | Nghị định 141/2026/NĐ-CP có hiệu lực từ ngày nào? | A | 0.00 | 0.99 | 0.50 | 1.00 | evaluation | Câu trả lời "01/01/2026 [1]" đúng và chunk top 1 chứa nguyên văn "có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026". Judge flash-lite vẫn chấm 0; cùng câu trả lời ở B được 1.0. Đây là lỗi của judge, không phải của pipeline. |
|   3 | Hộ kinh doanh có nhiều cửa hàng thì dùng mã số thuế trên hóa đơn thế nào? | A | 1.00 | 0.93 | 0.00 | 1.00 | retrieval | Dense lấy các chunk nói chung về hóa đơn/mã số thuế (NĐ 68 chunk-29, NĐ 254) nhưng thiếu đoạn "ghi rõ mã địa điểm kinh doanh" mà reference yêu cầu. B khắc phục được nhờ BM25 (recall 1.0). |

### Sửa sau lượt đánh giá (chưa chấm lại)

Lỗi #1 đã được sửa sau lượt chấm ở trên. Điểm trong bảng là của phiên bản trước khi sửa; chưa chấm lại vì hạn mức free tier.
- **Data:** `AMENDMENTS` trong `src/task4_chunking_indexing.py` gắn ghi chú sửa đổi của NĐ 141 vào 17 chunk NĐ 68 có cụm "500 triệu đồng". Chỉ 17 chunk này được embed lại; index lại hai lần vẫn giữ nguyên 529 chunk.
- **Prompt:** thêm quy tắc ưu tiên văn bản sửa đổi, áp dụng ghi chú sửa đổi cho cả bài báo cũ, và bắt buộc citation dạng `[n]`. Đầu ra dạng `[Document n]` được chuẩn hoá về `[n]`.
- **Kiểm tra thủ công:**
  - Câu golden 1 giờ trả lời "từ 01 tỷ đồng trở xuống không phải nộp thuế GTGT và TNCN [1]… mức 500 triệu đồng trước đây đã được thay thế".
  - Chỉ riêng quy tắc prompt thì không đủ: 4/4 lần chạy vẫn trả lời 500 triệu. Cần thêm ghi chú ở tầng data.

## Recommendations

| Priority | Action | Evidence from failure analysis | Expected impact | How to verify |
| -------: | ------ | ------------------------------ | --------------- | ------------- |
| 1 | (a) Thêm quy tắc vào prompt: khi các nguồn mâu thuẫn về con số, ưu tiên văn bản sửa đổi hoặc ban hành sau và nêu rõ mức cũ đã bị thay; đưa ngày ban hành vào nhãn Document. (b) Hợp nhất văn bản sửa đổi vào văn bản gốc trước khi chunk (áp dụng "thay cụm từ" của NĐ 141 vào NĐ 68), hoặc gắn metadata `amended_by` | Worst #1: mức 01 tỷ có trong context nhưng cả A và B vẫn trả lời mức 500 triệu đã hết hiệu lực | Câu hỏi về ngưỡng thuế trả lời đúng mức 01 tỷ; loại bỏ lỗi sai nghiêm trọng nhất của chatbot | Câu golden 1 có context recall > 0 và câu trả lời chứa "01 tỷ"; thêm 2–3 câu golden khác về điều khoản đã bị sửa |
| 2 | Dùng judge mạnh hơn (hoặc chấm 2–3 lần rồi lấy trung bình) và tăng `strictness` của answer relevancy lên 3 | Worst #2 và câu 15 ở A: câu trả lời đúng bị chấm faithfulness 0 | Điểm ổn định hơn, delta A/B phản ánh retrieval thay vì nhiễu judge | Chấm lại cùng file `runs/*.json` 2 lần; độ lệch từng câu < 0.1 |
| 3 | Giữ hybrid + RRF làm mặc định và thêm reranker (cross-encoder, ví dụ Jina/BGE reranker) sau RRF | Context precision chỉ đạt 0.76–0.80. Ví dụ ở Config A: câu 5 chỉ đạt 0.25 vì chunk trả lời (NĐ 141 chunk-3, hạn 30 ngày) đứng hạng 4, sau ba chunk tin tức article_08/article_04; câu 14 (0.33) và câu 13 (0.53) cũng có chunk liên quan bị đẩy xuống dưới chunk tin tức cùng chủ đề | Precision tăng, context gọn hơn cho generator | So sánh context precision B và B + reranker trên cùng 15 câu |

## Bonus experiments

| Experiment | Baseline | Metric delta | Latency/cost delta | Conclusion |
| ---------- | -------- | -----------: | -----------------: | ---------- |
| Không thực hiện bonus experiment trong lần chạy này | — | — | — | Reranker/HyDE là bước tiếp theo (Recommendation 3) |
