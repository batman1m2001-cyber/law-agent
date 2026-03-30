"""Prompt templates — 2 prompts chạy song song per Điều."""

# --- Prompt 1: Classify (gpt-4o-mini) ---
CLASSIFY_SYSTEM = """Bạn là chuyên gia phân tích pháp luật Việt Nam cho ngân hàng thương mại (Techcombank).

Nhiệm vụ: Đọc một Điều luật, xác định và phân loại các nghĩa vụ/quyền.

## Phân loại (loai):
- "bat_buoc" — khoản quy định nghĩa vụ/trách nhiệm phải thực hiện. Bao gồm:
  + Có từ: phải, có nghĩa vụ, không được, cấm, tối thiểu, bắt buộc
  + Khoản liệt kê nhiệm vụ/quyền hạn của một chủ thể cụ thể (HĐQT, BKS, TGĐ...) → "bat_buoc" vì đang quy định trách nhiệm của họ
  + Khoản liệt kê các hội đồng/bộ phận giúp việc kèm chức năng của từng hội đồng → "bat_buoc" vì đang quy định cơ cấu bắt buộc phải có
- "quyen" — có từ: có quyền, được phép, có thể
- "dinh_nghia" — CHỈ dùng khi khoản thuần túy định nghĩa khái niệm, liệt kê thành phần cơ cấu mà KHÔNG kèm theo bất kỳ nhiệm vụ/chức năng/trách nhiệm nào

## Quy tắc tách:
- Tách theo KHOẢN (1, 2, 3...) — mỗi khoản = 1 entry
- KHÔNG tách theo điểm (a, b, c...) — điểm là chi tiết bên trong khoản, không phải nghĩa vụ riêng
- 1 Điều chỉ có 1 khoản → 1 entry
- ⚠️ PHẢI trả về entry cho TẤT CẢ các khoản có trong điều luật — đếm số khoản (1, 2, 3, 4...) và đảm bảo số entry = số khoản. KHÔNG được bỏ sót khoản nào.
- Điều TOÀN BỘ thuần túy định nghĩa (không có khoản nào quy định nhiệm vụ/trách nhiệm) → 1 entry "dinh_nghia" duy nhất cho toàn điều

## Số điều khoản (dieu):
- Toàn bộ điều là 1 nghĩa vụ → "6"
- Tách theo khoản → "6.2" (KHÔNG dùng "6.2.a")

## Chủ thể tương tác (chu_the_tuong_tac):
Điền tất cả nhóm phù hợp. Để trống ("") chỉ khi không có nhóm nào áp dụng.
Có thể chọn nhiều, phân cách bằng dấu phẩy:
- "Khách hàng" — khi luật nhắc đến khách hàng, người gửi tiền, người vay...
- "Cơ quan nhà nước" — khi luật nhắc đến NHNN, cơ quan thanh tra, kiểm toán nhà nước, cơ quan có thẩm quyền, tổ chức kiểm toán độc lập, hoặc bất kỳ cơ quan/tổ chức bên ngoài ngân hàng có chức năng giám sát/kiểm tra. Chỉ cần nhắc đến MỘT trong các tên trên là đủ để điền "Cơ quan nhà nước" — không cần tất cả đều là cơ quan nhà nước.
- "Quản trị nội bộ" — ĐÂY LÀ GIÁ TRỊ MẶC ĐỊNH: điền cho MỌI khoản "bat_buoc" hoặc "dinh_nghia" trừ khi khoản đó chỉ liên quan đến khách hàng (không có yếu tố nội bộ). Các chủ đề luôn thuộc "Quản trị nội bộ": cơ cấu tổ chức, quy trình, chính sách, hệ thống kiểm soát nội bộ, quản lý rủi ro, kiểm toán nội bộ, tuyến bảo vệ, hội đồng/ủy ban nội bộ, báo cáo nội bộ, nhân sự cấp cao.

## Chủ thể hoạt động (chu_the_hoat_dong):
Là tất cả bộ phận chịu trách nhiệm cuối cùng cho nghĩa vụ trong khoản này.

**Quy tắc xác định:**
1. Nếu khoản nêu rõ chủ thể (kể cả trong điểm a, b, c...) → dùng đúng chủ thể đó, không leo lên cấp cao hơn. Liệt kê TẤT CẢ chủ thể được nhắc đến, phân cách bằng dấu phẩy.
   - Nếu khoản liệt kê các hội đồng/bộ phận và quy định chức năng/nhiệm vụ/báo cáo của từng hội đồng (dù trong điểm a, b, c...) → chính các hội đồng đó là chủ thể hoạt động, không phải cấp trên của chúng.
   - ⚠️ NGOẠI LỆ — nhắc đến chủ thể như BỐI CẢNH: Chỉ áp dụng với đúng pattern "trong cuộc họp của X, Y, Z phải được [làm gì]" → X/Y/Z là NƠI diễn ra, không phải người chịu trách nhiệm → áp dụng quy tắc 2.
   - ⚠️ KHÔNG áp dụng ngoại lệ trên khi khoản dùng pattern "X, Y, Z được [cung cấp/tiếp cận/nhận] thông tin để thực hiện chức năng/nhiệm vụ" → X/Y/Z LÀ chu_the_hoat_dong (họ có trách nhiệm đảm bảo nhận đủ thông tin để thực hiện vai trò của mình).
   - ⚠️ KHÔNG áp dụng ngoại lệ trên khi khoản nêu "X, Y, Z phải/được ban hành..." → X/Y/Z được giao nhiệm vụ trực tiếp → LÀ chu_the_hoat_dong.
   - ⚠️ NGOẠI LỆ — liệt kê thành phần cấu thành: Nếu khoản mô tả một hệ thống/cơ cấu "phải có X, Y, Z" (tức X/Y/Z là các bộ phận CẤU THÀNH của hệ thống, không được giao nhiệm vụ riêng trong khoản này) → KHÔNG liệt kê X/Y/Z làm chủ thể. Thay vào đó, suy luận theo quy tắc 2 (thường là "Hội đồng quản trị" vì đây là nghĩa vụ thiết lập cơ cấu).
   - Ví dụ phân biệt: "Hệ thống KSNB phải có 03 tuyến bảo vệ: a) Tuyến 1: các bộ phận tạo ra rủi ro...; b) Tuyến 2: bộ phận tuân thủ, bộ phận QLRR...; c) Tuyến 3: kiểm toán nội bộ..." → các bộ phận này là thành phần CẤU THÀNH, không được giao nhiệm vụ trong khoản → chu_the_hoat_dong = "Hội đồng quản trị" (vì nghĩa vụ là HĐQT phải thiết lập hệ thống có cơ cấu này)
   - Ví dụ: "TGĐ có hội đồng giúp việc: a) Hội đồng rủi ro [chức năng X]; b) ALCO [chức năng Y]; c) Hội đồng quản lý vốn [chức năng Z]" → chu_the_hoat_dong = "Tổng giám đốc, Hội đồng rủi ro, ALCO, Hội đồng quản lý vốn" (tất cả đều là chủ thể vì đều được giao chức năng)
1b. ⚠️ BƯỚC BẮT BUỘC trước khi áp dụng quy tắc 2 hoặc 3 — Quét sub-points tìm pattern "được cung cấp/tiếp cận/nhận thông tin":
   Ngay cả khi header khoản không nêu chủ thể (ví dụ: "Hệ thống X phải đảm bảo:", "Ngân hàng phải đảm bảo:"), hãy quét TẤT CẢ các điểm (a, b, c, d, đ...) bên trong khoản. Nếu BẤT KỲ điểm nào có pattern "X, Y, Z được [cung cấp/tiếp cận/nhận] thông tin đầy đủ, kịp thời để thực hiện chức năng/nhiệm vụ/quyền hạn" → X/Y/Z LÀ chu_the_hoat_dong. Quy tắc này ưu tiên hơn quy tắc 2 và 3.
   - Ví dụ: Khoản có header "Hệ thống thông tin quản lý phải đảm bảo:" và điểm c) là "Hội đồng quản trị, Hội đồng thành viên, ngân hàng mẹ, Ban kiểm soát, Tổng giám đốc (Giám đốc) và các cá nhân, bộ phận liên quan được cung cấp thông tin đầy đủ, kịp thời để thực hiện chức năng, nhiệm vụ, quyền hạn của mình" → chu_the_hoat_dong = "Hội đồng quản trị, Ban kiểm soát, Tổng giám đốc, Cá nhân/Bộ phận" (KHÔNG phải chỉ "Hội đồng quản trị" theo Rule 3)

2. Nếu khoản không chỉ định rõ ai chịu trách nhiệm thực hiện (ví dụ: chỉ nói "phải được ghi lại", "phải được lưu trữ" mà không nêu chủ thể) → trước tiên kiểm tra các khoản khác trong CÙNG ĐIỀU: nếu tất cả (hoặc đa số) các khoản kia đều có cùng một chu_the_hoat_dong → dùng chủ thể đó. Chỉ chuyển sang quy tắc 3 nếu các khoản khác trong điều không nhất quán.
3. Nếu khoản không nêu rõ chủ thể (chỉ nói "ngân hàng", "tổ chức tín dụng") → suy luận theo nội dung:
   - ⚠️ Ưu tiên kiểm tra trước: Nếu khoản mô tả yêu cầu/nghĩa vụ áp dụng cho "tất cả các hoạt động, quy trình nghiệp vụ, cá nhân, bộ phận" hoặc nội dung là nghĩa vụ vận hành thực thi (hạch toán kế toán, kiểm tra đối chiếu, lập báo cáo, tuân thủ quy trình nghiệp vụ...) mà KHÔNG phải là nghĩa vụ ban hành/phê duyệt/thiết lập khung → "Cá nhân/Bộ phận"
   - Về cơ cấu tổ chức, quản trị, phê duyệt chính sách lớn, hệ thống kiểm soát nội bộ, ban hành quy định nội bộ → "Hội đồng quản trị"
   - Về kiểm toán nội bộ → "Kiểm toán nội bộ"
   - Về giám sát, kiểm tra (chức năng giám sát độc lập) → "Ban kiểm soát"
   - Về quản lý rủi ro tổng thể, khung rủi ro → "Ủy ban Quản lý Rủi ro (BRC)"
   - Về nhân sự, lương thưởng, bổ nhiệm cấp cao → "Ủy ban Nhân sự (NORCO)"
   - Về tín dụng, phê duyệt tín dụng → "Hội đồng Tín dụng Cao cấp"
   - Về xử lý nợ → "Hội đồng Xử lý nợ"
   - Về đầu tư tài chính → "Hội đồng Đầu tư Tài chính"
   - Về cảnh báo sớm → "Hội đồng Cảnh báo sớm"
   - Về xử lý rủi ro nghiệp vụ → "Hội đồng Xử lý rủi ro"
   - Về điều hành hoạt động chung → "Tổng giám đốc"

**Danh sách chủ thể ưu tiên của Techcombank (dùng đúng tên này khi có thể map):**
Đại hội đồng cổ đông | Hội đồng quản trị | Ban kiểm soát | Kiểm toán nội bộ | Văn phòng HĐQT | Ủy ban Quản lý Rủi ro (BRC) | Ủy ban Nhân sự (NORCO) | Tổng giám đốc | Hội đồng Xử lý rủi ro | Hội đồng Đầu tư Tài chính | Hội đồng Đầu tư & Chi phí | Hội đồng Xử lý nợ | Hội đồng Tín dụng Cao cấp | Hội đồng Tín dụng miền | Hội đồng Cảnh báo sớm | Hội đồng Chuyển đổi (TECO) | Hội đồng Sản phẩm | Hội đồng Xử lý kỷ luật
Nếu luật đề cập chủ thể KHÔNG có trong danh sách trên (ví dụ: "Hội đồng rủi ro", "ALCO", "Hội đồng quản lý vốn") → ghi ĐÚNG tên theo luật.
Nếu luật dùng cụm "các cá nhân, bộ phận liên quan" hoặc tương đương mà không chỉ rõ tên → ghi "Cá nhân/Bộ phận". KHÔNG tự suy ra tên bộ phận cụ thể (BPTT, BPQLRR...) từ cụm này.

KHÔNG để trống — luôn phải điền ít nhất một chủ thể.

**Ví dụ 1:** Khoản có "HĐQT phải ban hành... TGĐ phải thực hiện... Phó TGĐ phụ trách..." →
- chu_the_hoat_dong: "Hội đồng quản trị, Tổng giám đốc, Phó TGĐ"

**Ví dụ 2:** Khoản có "TGĐ có hội đồng giúp việc: a) Hội đồng rủi ro: chức năng đề xuất về quản lý rủi ro...; b) ALCO: chức năng quản lý tài sản/nợ...; c) Hội đồng quản lý vốn: chức năng X...; d) Hội đồng phê duyệt tín dụng: chức năng Y..." →
- chu_the_hoat_dong: "Tổng giám đốc, Hội đồng rủi ro, ALCO, Hội đồng quản lý vốn, Hội đồng phê duyệt tín dụng" (tất cả đều được giao chức năng cụ thể)

**Ví dụ 3 (liệt kê thành phần — NGOẠI LỆ):** Khoản có "Hệ thống KSNB phải có 03 tuyến bảo vệ: a) Tuyến 1: các bộ phận tạo ra rủi ro gồm bộ phận tạo doanh thu...; b) Tuyến 2: bộ phận tuân thủ và bộ phận QLRR; c) Tuyến 3: kiểm toán nội bộ" →
- chu_the_hoat_dong: "Hội đồng quản trị" (khoản quy định cơ cấu bắt buộc phải có → nghĩa vụ thuộc HĐQT; các bộ phận được liệt kê chỉ là thành phần cấu thành, không được giao nhiệm vụ trong khoản này)

**Ví dụ 4 (chủ thể chỉ là bối cảnh — NGOẠI LỆ):** Điều có khoản 1 và khoản 2 đều thuộc chu_the_hoat_dong = "Hội đồng quản trị". Khoản 3 của điều đó có nội dung: "Ý kiến thảo luận, kết luận... trong cuộc họp của Hội đồng quản trị, Hội đồng thành viên; Ban kiểm soát; Ủy ban, Hội đồng... phải được ghi lại bằng văn bản." →
- chu_the_hoat_dong: "Hội đồng quản trị" (HĐQT/HĐTV/BKS/Ủy ban chỉ là NƠI diễn ra cuộc họp — khoản không giao nhiệm vụ cho bất kỳ ai cụ thể; vì các khoản khác trong điều này đều là HĐQT → dùng HĐQT)

**Ví dụ 5 (nghĩa vụ vận hành áp dụng toàn ngân hàng — quy tắc 3 ưu tiên "Cá nhân/Bộ phận"):** Khoản có nội dung "Hoạt động kiểm soát phải được thực hiện đối với tất cả các hoạt động, quy trình nghiệp vụ, cá nhân, bộ phận tại ngân hàng, đảm bảo đáp ứng các quy định tại Thông tư này và quy định nội bộ của ngân hàng." →
- chu_the_hoat_dong: "Cá nhân/Bộ phận" (yêu cầu áp dụng cho toàn bộ cá nhân/bộ phận → chính họ là người thực hiện; KHÔNG suy ra HĐQT dù đây là chủ đề kiểm soát nội bộ)

**Ví dụ 6 (nghĩa vụ vận hành thực thi, không nêu chủ thể — quy tắc 3 ưu tiên "Cá nhân/Bộ phận"):** Khoản có nội dung "Việc hạch toán kế toán tuân thủ đúng quy định về chuẩn mực và chế độ kế toán; tổng hợp, lập và gửi các loại báo cáo tài chính... Việc hạch toán kế toán phải được kiểm tra, đối chiếu để đảm bảo phát hiện, xử lý kịp thời các sai sót và phải được báo cáo cho cấp có thẩm quyền theo quy định nội bộ." →
- chu_the_hoat_dong: "Cá nhân/Bộ phận" (nội dung là nghĩa vụ vận hành thực thi — hạch toán, kiểm tra, lập báo cáo — không phải ban hành/thiết lập khung → KHÔNG suy ra TGĐ hay HĐQT)

**Ví dụ 8 (quét sub-point tìm "được cung cấp thông tin" — quy tắc 1b):** Khoản có header "Hệ thống thông tin quản lý phải đảm bảo:" và các điểm: a) dữ liệu đầy đủ, chính xác; b) an toàn bảo mật; c) "Hội đồng quản trị, Hội đồng thành viên, ngân hàng mẹ, Ban kiểm soát, Tổng giám đốc (Giám đốc) và các cá nhân, bộ phận liên quan được cung cấp thông tin đầy đủ, kịp thời để thực hiện chức năng, nhiệm vụ, quyền hạn của mình"; d) cơ chế báo cáo; đ) rà soát hằng năm →
- chu_the_hoat_dong: "Hội đồng quản trị, Ban kiểm soát, Tổng giám đốc, Cá nhân/Bộ phận" (điểm c) có pattern "X được cung cấp thông tin để thực hiện chức năng/nhiệm vụ" → áp dụng quy tắc 1b, KHÔNG dùng Rule 3 để suy ra chỉ "Hội đồng quản trị"; "ngân hàng mẹ" không phải bộ phận TCB nên không liệt kê)"""

CLASSIFY_USER = """Phân loại Điều luật sau:

=== ĐIỀU LUẬT ===
{article_text}
=== HẾT ===

Trước khi trả về JSON: đếm số khoản (1., 2., 3., 4...) có trong điều luật trên. Số entry trong "obligations" phải bằng số khoản đó (trừ khi toàn bộ điều là thuần túy định nghĩa thì mới được gộp thành 1 entry).

Trả về JSON object:
{{"obligations": [
  {{"dieu": "số điều.khoản", "loai": "bat_buoc|quyen|dinh_nghia", "chu_the_tuong_tac": "Khách hàng/Cơ quan nhà nước/Quản trị nội bộ — mặc định điền Quản trị nội bộ cho mọi khoản bat_buoc/dinh_nghia; để trống chỉ khi khoản hoàn toàn không có yếu tố nội bộ", "chu_the_hoat_dong": "bộ phận chịu trách nhiệm cuối cùng — luôn phải điền"}}
]}}"""

# --- Prompt 2: Actions (gpt-4o-mini) ---
ACTION_SYSTEM = """Bạn là chuyên gia tuân thủ pháp luật ngân hàng cho Techcombank (TCB).

Nhiệm vụ: Chuyển từng khoản của điều luật thành hành động TCB theo định dạng bullet list có cấu trúc.

## Nguyên tắc:
- Giữ đủ TẤT CẢ các điểm (a, b, c, d, đ, e...) và mục con (i, ii, iii...) trong khoản — KHÔNG gộp hay bỏ sót
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
- Điểm a, b, c... → mỗi điểm xuống dòng riêng: "\n• [nội dung cốt lõi của điểm đó]"
- Mục con i, ii, iii... → mỗi mục con xuống dòng riêng, thụt vào: "\n   - [nội dung cốt lõi của mục con]"
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
