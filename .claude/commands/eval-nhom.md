# Evaluate nhom_nghia_vu accuracy

Evaluate the nhom_nghia_vu classification accuracy of the LLM predict file against the true label file.

## Inputs

- **True label file**: `/Users/tramynguyen/Work/extract_test_file/Label for law agent.xlsx`
  - Sheet "Trang tính1" contains 13 nhóm definitions with Điều ranges per law type (TCTD, DN, CK)
  - TCTD = Tổ chức tín dụng, CK = Luật chứng khoán, DN = Luật doanh nghiệp
- **Predict file**: $ARGUMENTS (path to NghiaVu_*.xlsx output file from the extraction pipeline)
  - If no argument given, look for the most recent NghiaVu_*.xlsx in `/Users/tramynguyen/Work/extract_test_file/`

## Label file parsing

Parse Sheet "Trang tính1" to build a Điều → list of acceptable nhóm mapping. Structure:
- Rows with col A starting with "NHÓM" = group header (e.g. "NHÓM 1: CẤP PHÉP & GIA NHẬP THỊ TRƯỜNG")
- Under each group, rows with col A = "TCTD"/"DN"/"CK" and col B = description with Điều ranges
- Extract Điều ranges from col B using pattern `Đ.X-Y` or `Đ.X` (e.g. "Đ.27-37" → range 27 to 37)
- **For now, only use TCTD rows** since we're evaluating TCTD law documents
- A single Điều can belong to MULTIPLE nhóm (overlapping ranges are valid)

The nhóm short name is extracted from the header: "NHÓM 1: CẤP PHÉP & GIA NHẬP THỊ TRƯỜNG" → "CẤP PHÉP & GIA NHẬP THỊ TRƯỜNG"

Known TCTD Điều ranges:
```
CẤP PHÉP & GIA NHẬP THỊ TRƯỜNG         → Đ.27-37
QUẢN TRỊ CÔNG TY                        → Đ.38-73
SỞ HỮU CỔ PHẦN & NGƯỜI CÓ LIÊN QUAN   → Đ.63-65
HOẠT ĐỘNG KINH DOANH NGÂN HÀNG         → Đ.74-97, Đ.15
AN TOÀN VỐN & CÁC TỶ LỆ BẢO ĐẢM AN TOÀN → Đ.126-147
GÓP VỐN, MUA CỔ PHẦN VÀO DN KHÁC       → Đ.109-115, Đ.137-139
PHÁT HÀNH CHỨNG KHOÁN & HUY ĐỘNG VỐN   → Đ.37
CÔNG BỐ THÔNG TIN & BÁO CÁO            → Đ.152
GIAO DỊCH NLQ & CHỐNG XUNG ĐỘT LỢI ÍCH → Đ.129-136
NIÊM YẾT & GIAO DỊCH CHỨNG KHOÁN       → (no specific range)
TỔ CHỨC LẠI, GIẢI THỂ, PHÁ SẢN         → Đ.200-207
XỬ LÝ NỢ XẤU & TÀI SẢN BẢO ĐẢM       → Đ.195-198c (treat 198a-198c as 195-199)
PHÒNG CHỐNG RỬA TIỀN & BẢO VỆ KHÁCH HÀNG → Đ.10, Đ.13-14
```

## Predict file parsing

- Row 2 = headers, data starts row 3
- Col C = "Số điều khoản" (e.g. "29.1", "198a.5")
- Col G = "Có bắt buộc hay không" — "x" means bat_buoc/quyen, empty means dinh_nghia/khong_ap_dung
- Col J = "Nhóm nghĩa vụ" — LLM prediction
- Col K = "Lý do nhóm nghĩa vụ" — chain of thought reasoning

## Evaluation logic

For each row in the predict file:
1. Extract article number from dieu: "29.1" → 29, "198a.5" → "198a" (handle letter suffixes)
2. **SKIP if Col G is empty** (dinh_nghia/khong_ap_dung — user doesn't want to evaluate these)
3. **SKIP if Col J is empty** (LLM returned no nhom — this is a "missing" case, not a contradiction)
4. **EVALUATE if Col G = "x" AND Col J has a value**: look up the article number in the label mapping
   - If the LLM's nhom matches ANY of the acceptable nhóm for that Điều → **CORRECT**
   - If the LLM's nhom does NOT match any acceptable nhóm → **WRONG**
   - If the Điều is not found in any label range → **UNMAPPED** (can't evaluate)

## Nhom name matching

The predict file and label file may use slightly different nhom names. Use fuzzy matching:
- Normalize: uppercase, strip whitespace
- Match on key substring: e.g. "GIAO DỊCH NLQ" matches both "GIAO DỊCH NLQ & CHỐNG XUNG ĐỘT LỢI ÍCH" and "GIAO DỊCH VỚI NGƯỜI CÓ LIÊN QUAN & CHỐNG XUNG ĐỘT LỢI ÍCH"
- Build a mapping of known aliases if needed

## Output

Print a summary report:

```
=== NHÓM NGHĨA VỤ EVALUATION ===
Predict file: <path>
Label file: <path>

Total rows:          X
Skipped (dinh_nghia/khong_ap_dung): X
Skipped (J empty):   X
Evaluated:           X

✅ Correct:          X (Y%)
❌ Wrong:            X (Y%)
⚠️  Unmapped:        X

=== WRONG PREDICTIONS (detail) ===
Điều | LLM Prediction | Acceptable nhóm(s) | LLM ly_do
...

=== ACCURACY BY NHÓM ===
Nhóm | Correct | Wrong | Accuracy
...
```

Focus the detailed output on the WRONG predictions — these are the contradictions the user wants to analyze.
