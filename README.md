# Law Agent - Trích xuất Nghĩa vụ Tuân thủ Pháp luật

Hệ thống tự động đọc văn bản pháp luật Việt Nam (.doc/.docx), sử dụng LLM (OpenAI GPT-4o) để phân tích và trích xuất danh mục nghĩa vụ tuân thủ cho ngân hàng thương mại, xuất kết quả ra file Excel theo format chuẩn.

## Tính năng

- **Đọc file .doc (OLE binary) và .docx** — parse trực tiếp, không cần cài thêm phần mềm
- **Tự động nhận diện metadata** — tên văn bản, số hiệu, ngày hiệu lực
- **Chunking thông minh** — tách văn bản theo cấu trúc Chương/Mục/Điều
- **2-node LLM pipeline**:
  - Node 1: Phân loại nghĩa vụ (bắt buộc / quyền / bỏ qua) + trích nguyên văn
  - Node 2: Sinh hành động cụ thể cho TCB
- **Streaming UI** — kết quả hiển thị real-time theo từng chunk
- **Timeline** — theo dõi thời gian từng LLM call
- **Xuất Excel** — format chuẩn với 7 cột, zebra rows, freeze panes

## Cài đặt

Yêu cầu: Python >= 3.10, [uv](https://docs.astral.sh/uv/)

```bash
# Clone repo
git clone https://github.com/batman1m2001-cyber/law-agent.git
cd law-agent

# Cài dependencies
uv sync

# Tạo file .env
cp .env.example .env
# Sửa .env, thêm OPENAI_API_KEY
```

## Cấu hình

Tạo file `.env` với nội dung:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o          # (tùy chọn, mặc định gpt-4o)
```

## Sử dụng

```bash
uv run python app.py
```

Mở trình duyệt tại `http://127.0.0.1:7860`:

1. Upload file văn bản pháp luật (.doc hoặc .docx)
2. Bấm **Phân tích**
3. Theo dõi tiến trình real-time trên panel trái
4. Xem kết quả trên bảng panel phải
5. Tải file Excel khi hoàn tất

## Cấu trúc dự án

```
law-agent/
├── app.py                  # Gradio UI
├── src/
│   ├── document_reader.py  # Đọc .doc (OLE) và .docx
│   ├── chunker.py          # Tách văn bản theo Chương/Mục/Điều
│   ├── prompts.py          # Prompt templates (2-node)
│   ├── extractor.py        # LLM pipeline + streaming
│   └── excel_writer.py     # Tạo Excel có format
├── data/                   # File mẫu và demo
├── pyproject.toml
└── .env                    # API keys (không commit)
```

## Output Excel

| Cột | Nội dung |
|-----|----------|
| Tên văn bản | Tên đầy đủ của văn bản pháp luật |
| Số văn bản | Số hiệu (VD: 83/2025/TT-NHNN) |
| Số điều khoản | Số điều/khoản/điểm (VD: 6.2.a) |
| Ngày hiệu lực | Ngày văn bản có hiệu lực |
| Nghĩa vụ pháp luật | Trích nguyên văn từ văn bản gốc |
| Hành động TCB | Hành động cụ thể cần thực hiện |
| Bắt buộc/Quyền | Phân loại nghĩa vụ |
