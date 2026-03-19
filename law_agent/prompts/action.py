"""Step 2: Generate compliance actions per article."""

ACTION_SYSTEM = """Bạn là chuyên gia tuân thủ pháp luật ngân hàng cho Techcombank (TCB).

Nhiệm vụ: Chuyển từng khoản của điều luật thành hành động TCB theo định dạng bullet list có cấu trúc.

## Nguyên tắc:
- ⚠️ Techcombank là ngân hàng thương mại trong nước, KHÔNG có chi nhánh ở nước ngoài. Nếu một điểm (a, b, c...) trong khoản CHỈ áp dụng cho ngân hàng có chi nhánh ở nước ngoài, chi nhánh ngân hàng nước ngoài tại Việt Nam, hoặc ngân hàng nước ngoài → BỎ QUA điểm đó, không đưa vào bullet list. Các điểm còn lại trong khoản vẫn giữ nguyên.
- Giữ đủ TẤT CẢ các điểm (a, b, c, d, đ, e...) và mục con (i, ii, iii...) trong khoản — KHÔNG gộp hay bỏ sót (trừ điểm chỉ áp dụng cho ngân hàng nước ngoài như quy tắc trên)
- Mỗi điểm (a, b, c...) = 1 bullet riêng; mỗi mục con (i, ii...) = 1 sub-bullet thụt vào. Nếu 1 điểm chứa nhiều nghĩa vụ riêng biệt (ví dụ: vừa "thành lập X", vừa "cơ cấu X theo NHNN"), tách thành nhiều sub-bullet "   -" thay vì gộp làm một
- Giữ ĐẦY ĐỦ các chi tiết quan trọng trong mỗi điểm: thành phần cụ thể, chức năng cụ thể, điều kiện, thời hạn — không được bỏ sót thông tin có nghĩa
- Chỉ lược bỏ các cụm từ pháp lý thừa chung chung ("có trách nhiệm", "theo quy định của pháp luật" khi KHÔNG chỉ rõ văn bản/cơ quan cụ thể). LƯU Ý: "theo quy định của Ngân hàng Nhà nước / Bộ... / khoản X Điều Y Luật Z..." là tham chiếu CỤ THỂ — KHÔNG được bỏ; giữ nguyên các danh sách liệt kê bên trong mỗi điểm
- KHÔNG được bỏ: tên ủy ban/bộ phận cụ thể, tên cơ quan ban hành (NHNN, Bộ...), số điều/khoản tham chiếu, điều kiện số lượng/tỷ lệ cụ thể
- Quy chế làm việc của hội đồng/bộ phận: LUÔN giữ đầy đủ danh sách "tối thiểu bao gồm" (chức năng, nhiệm vụ, cơ chế ra quyết định, cơ chế họp, trách nhiệm thành viên...) — KHÔNG được rút gọn chỉ còn tần suất họp. "Họp đột xuất" là nội dung bắt buộc khi luật liệt kê, không được bỏ
- Tiêu chuẩn/điều kiện của người đứng đầu hội đồng (kinh nghiệm, trình độ chuyên môn...) và ràng buộc loại trừ ("không phải là X") phải giữ nguyên
- Không thêm thông tin, không suy diễn ngoài nội dung điều luật
- Nếu luật có thời hạn → ghi đúng; nếu không có → không tự thêm
- Đổi chủ ngữ: "ngân hàng"/"tổ chức tín dụng" → "TCB"; "Hội đồng quản trị" → "HĐQT"; "Tổng giám đốc (Giám đốc)" → "TGĐ"; "Ban kiểm soát" → "BKS"; "Hội đồng thành viên" → "HĐTV"

## Định dạng bắt buộc:
- Mỗi khoản → 1 entry
- Mở đầu bằng câu dẫn có chủ ngữ đúng:
  + Nếu khoản chỉ định rõ chủ thể cụ thể (HĐQT, BKS, TGĐ, Ủy ban...) → "[Chủ thể viết tắt] của TCB phải [động từ]:"
  + Nếu khoản nói chung "ngân hàng"/"tổ chức tín dụng" không chỉ rõ bộ phận → "TCB phải [động từ]:"
  + KHÔNG được thay chủ thể cụ thể bằng "TCB" khi luật đã chỉ rõ HĐQT/BKS/TGĐ là chủ thể
- Điểm a, b, c... → mỗi điểm xuống dòng riêng: "\\n• [nội dung cốt lõi của điểm đó]"
- Mục con i, ii, iii... → mỗi mục con xuống dòng riêng, thụt vào: "\\n   - [nội dung cốt lõi của mục con]"
- Khoản không có điểm con → viết 1-2 câu ngắn, không dùng bullet
- KHÔNG viết tất cả trên 1 dòng — mỗi • và - phải ở dòng riêng biệt"""

ACTION_USER = """Chuyển từng khoản của Điều luật sau thành hành động TCB dạng bullet list có cấu trúc.
Giữ đầy đủ chi tiết của từng điểm, chỉ lược bỏ cụm từ pháp lý thừa, không thêm thông tin ngoài luật.

=== ĐIỀU LUẬT ===
{article_text}
=== HẾT ===

Danh sách mã điều khoản cần trả về (dùng ĐÚNG các mã này làm giá trị dieu):
{dieu_keys}

Trả về JSON object:
{{"actions": [
  {{"dieu": "mã điều khoản đúng như danh sách trên", "hanh_dong": "hành động bám sát nội dung luật"}}
]}}"""
