# Prompt Template: Suy ra nghĩa vụ tuân thủ từ văn bản pháp luật cho Techcombank

## Cách dùng
Copy toàn bộ phần "=== PROMPT ===" bên dưới, thay thế các giá trị trong `[ ]`, rồi gửi cho Claude Code.

---

## === PROMPT ===

Tôi có file văn bản pháp luật: `[TÊN FILE, VD: 38.2024.TT.NHNN.doc]`
Hãy đọc file đó và tạo file Excel danh mục nghĩa vụ tuân thủ cho **Techcombank** (ngân hàng thương mại).

### Thông tin văn bản
- **Tên văn bản:** [VD: Thông tư về hoạt động tư vấn của tổ chức tín dụng]
- **Số văn bản:** [VD: 38/2024/TT-NHNN]
- **Ngày hiệu lực:** [VD: 01/07/2024]

### Cấu trúc file Excel output
File có 7 cột, từ hàng 1:
| Cột | Tên cột | Nội dung |
|-----|---------|---------|
| A | Tên văn bản | Tên đầy đủ của văn bản pháp luật |
| B | Số văn bản | Số hiệu văn bản |
| C | Số điều khoản | Số điều + khoản cụ thể, VD: `6`, `6.2`, `6.2.a` |
| D | Ngày hiệu lực | Định dạng DD/MM/YYYY |
| E | Nghĩa vụ pháp luật | Trích dẫn nguyên văn + tiêu đề điều khoản |
| F | Hành động Techcombank cần thực hiện | Hành động cụ thể, ngắn gọn, bắt đầu bằng động từ |
| G | Có bắt buộc hay không | `x` nếu bắt buộc, để trống nếu là quyền/tùy chọn |

### Quy tắc phân tích và tách nghĩa vụ

**1. Mỗi hàng = 1 nghĩa vụ độc lập**
- Không gom nhiều nghĩa vụ vào 1 hàng
- Nếu 1 điều có nhiều khoản/điểm, mỗi khoản/điểm là 1 hàng riêng
- Nếu 1 điều chỉ có 1 nội dung đơn giản thì để 1 hàng

**2. Xác định loại điều khoản**
- ✅ **Tạo hàng:** Điều khoản có từ `phải`, `có nghĩa vụ`, `không được`, `cấm`, `phải đảm bảo`, `phải xây dựng`, `phải thực hiện`, `phải gửi`, `phải có`, `phải ký`
- ✅ **Tạo hàng (Có bắt buộc = trống):** Điều khoản có từ `có quyền`, `được phép`, `có thể`
- ❌ **Bỏ qua:** Điều về phạm vi điều chỉnh (Điều 1), đối tượng áp dụng (Điều 2), định nghĩa/giải thích từ ngữ (Điều 3), tổ chức thực hiện (Điều cuối)

**3. Cột F — Hành động Techcombank**
- Bắt đầu bằng động từ hành động: `Ban hành`, `Xây dựng`, `Gửi`, `Ký`, `Niêm yết`, `Đào tạo`, `Giám sát`, `Cấm`, `Không được`...
- Cụ thể, có thể kiểm tra được (auditable)
- Nêu rõ: làm gì, với ai, trong thời hạn nào (nếu có)
- Không dùng "TCB phải" ở đầu — bắt đầu thẳng bằng động từ

**4. Cột C — Số điều khoản**
- Chỉ ghi số điều nếu toàn bộ điều là 1 nghĩa vụ: `6`
- Ghi đến khoản nếu tách theo khoản: `6.2`
- Ghi đến điểm nếu tách theo điểm: `6.2.a`

**5. Format file Excel**
- Hàng 1: Tiêu đề `Nghĩa vụ pháp luật` — merge toàn bộ 7 cột, in đậm, cỡ 13
- Hàng 2: Header — nền màu `4472C4`, chữ trắng, in đậm
- Hàng 3+: Dữ liệu — zebra rows (trắng / `DCE6F1`), wrap text, border mỏng
- Freeze 2 hàng đầu
- Độ rộng cột: A=30, B=18, C=14, D=14, E=55, F=55, G=15
- Ngày hiệu lực format: DD/MM/YYYY

### Ví dụ output mẫu (1 hàng)
| Tên văn bản | Số VB | Số điều | Ngày HL | Nghĩa vụ pháp luật | Hành động TCB | Bắt buộc |
|---|---|---|---|---|---|---|
| Thông tư về hoạt động tư vấn... | 38/2024/TT-NHNN | 6.1 | 01/07/2024 | "Điều 6, Khoản 1. Trước khi triển khai hoạt động tư vấn, tổ chức tín dụng phải xây dựng quy định nội bộ về hoạt động tư vấn." | Xây dựng và ban hành quy định nội bộ về hoạt động tư vấn trước khi triển khai dịch vụ tư vấn | x |

### File output
Lưu file tại: `/Users/tramynguyen/Work/Law_to_excel/Danh mục nghĩa vụ tuân thủ - [SỐ VĂN BẢN].xlsx`

---

## Ghi chú cải tiến so với lần trước

| Vấn đề cũ | Cải tiến |
|-----------|---------|
| Gom nhiều khoản vào 1 hàng (VD: Điều 5 có 6 nguyên tắc nhưng chỉ 1 hàng) | Mỗi nghĩa vụ độc lập = 1 hàng riêng |
| Cột F bắt đầu bằng "TCB phải:\n- ..." dài dòng | Bắt đầu thẳng bằng động từ, súc tích, auditable |
| Cột C chỉ ghi số điều (VD: `6`) dù điều có nhiều khoản | Ghi đến khoản/điểm cụ thể (VD: `6.2.a`) |
| Không phân biệt bắt buộc vs. quyền | Cột G = `x` nếu bắt buộc, trống nếu là quyền |
| Gồm cả điều về tổ chức thực hiện, định nghĩa | Bỏ qua các điều không tạo ra nghĩa vụ |
