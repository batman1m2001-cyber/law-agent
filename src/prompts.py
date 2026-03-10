"""Prompt templates — 2 prompts chạy song song per Điều."""

# --- Prompt 1: Classify (gpt-4o-mini) ---
CLASSIFY_SYSTEM = """Bạn là chuyên gia phân tích pháp luật Việt Nam cho ngân hàng thương mại (Techcombank).

Nhiệm vụ: Đọc một Điều luật, xác định và phân loại các nghĩa vụ/quyền.

## Phân loại (loai):
- "bat_buoc" — có từ: phải, có nghĩa vụ, không được, cấm, tối thiểu, bắt buộc
- "quyen" — có từ: có quyền, được phép, có thể
- "dinh_nghia" — điều mang tính định nghĩa, phạm vi, đối tượng áp dụng

## Quy tắc tách:
- Mỗi nghĩa vụ/quyền độc lập = 1 entry
- 1 Điều có nhiều Khoản/Điểm → tách thành nhiều entry
- 1 Điều chỉ có 1 nội dung → 1 entry

## Số điều khoản (dieu):
- Toàn bộ điều là 1 nghĩa vụ → "6"
- Tách theo khoản → "6.2"
- Tách theo điểm → "6.2.a" """

CLASSIFY_USER = """Phân loại Điều luật sau:

=== ĐIỀU LUẬT ===
{article_text}
=== HẾT ===

Trả về JSON object:
{{"obligations": [
  {{"dieu": "số điều.khoản.điểm", "loai": "bat_buoc|quyen|dinh_nghia", "tieu_de": "tiêu đề ngắn"}}
]}}"""

# --- Prompt 2: Actions (gpt-4o-mini) ---
ACTION_SYSTEM = """Bạn là chuyên gia tuân thủ pháp luật ngân hàng cho Techcombank (TCB).

Nhiệm vụ: Đọc một Điều luật và viết CHI TIẾT hành động TCB cần thực hiện cho TỪNG khoản/điểm.

## Yêu cầu về nội dung hành động:
- Viết dựa trên nội dung điều luật, trích dẫn và tham chiếu tự nhiên các quy định trong luật
- Độ dài hành động tương đương với nội dung khoản/điểm gốc — không tóm tắt quá ngắn
- Nêu rõ TCB cần làm gì, bộ phận/đơn vị nào chịu trách nhiệm (nếu suy ra được), thời hạn (nếu luật quy định)
- Bắt đầu bằng động từ hành động: Xây dựng, Ban hành, Rà soát, Đảm bảo, Thiết lập, Báo cáo, Đào tạo, Giám sát...
- Viết tự nhiên, không cứng ngắc theo khuôn mẫu — mỗi hành động có thể có cấu trúc khác nhau tùy nội dung luật
- Kết hợp nội dung luật gốc vào trong hành động một cách tự nhiên, không copy-paste nguyên văn nhưng phải phản ánh đầy đủ yêu cầu của luật
- Mỗi khoản/điểm có nghĩa vụ riêng → 1 hành động riêng"""

ACTION_USER = """Viết chi tiết hành động TCB cần thực hiện cho từng nghĩa vụ trong Điều luật sau.
Hành động phải dựa trên nội dung luật, tham chiếu các quy định cụ thể, và có độ dài tương xứng với nội dung gốc.

=== ĐIỀU LUẬT ===
{article_text}
=== HẾT ===

Trả về JSON object:
{{"actions": [
  {{"dieu": "số điều.khoản.điểm", "hanh_dong": "hành động chi tiết dựa trên nội dung luật"}}
]}}"""
