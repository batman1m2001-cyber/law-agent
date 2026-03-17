"""Create formatted Excel output from extracted obligations."""

import io
import re
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .extractor import Obligation

HEADERS = [
    "Tên văn bản",
    "Số văn bản",
    "Số điều khoản",
    "Ngày hiệu lực",
    "Nghĩa vụ pháp luật",
    "Hành động Techcombank cần thực hiện",
    "Có bắt buộc hay không",
    "Phân loại",
    "Chủ thể tương tác",
    "Chủ thể hoạt động",
]

_LOAI_LABEL = {
    "bat_buoc": "Nghĩa vụ",
    "quyen": "Quyền",
    "dinh_nghia": "Quy định chung",
}

COL_WIDTHS = [30, 18, 14, 14, 55, 55, 15, 18, 25, 25]

HEADER_FILL = PatternFill("solid", fgColor="4472C4")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
ALT_FILL = PatternFill("solid", fgColor="DCE6F1")
WHITE_FILL = PatternFill("solid", fgColor="FFFFFF")
def _parse_bold_markers(text: str) -> CellRichText | str:
    """Convert **bold** markers in text to Excel CellRichText with bold spans.

    Returns plain string if no markers found.
    """
    if "**" not in text:
        return text

    bold_font = InlineFont(b=True, sz=11)
    normal_font = InlineFont(sz=11)

    segments = re.split(r"\*\*", text)
    # Even indices = normal text, odd indices = bold text
    parts = []
    for i, seg in enumerate(segments):
        if not seg:
            continue
        font = bold_font if i % 2 == 1 else normal_font
        parts.append(TextBlock(font, seg))

    return CellRichText(*parts) if parts else text


def _strip_html(html: str) -> str:
    """Convert HTML to plain text for Excel cells."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)


def create_excel(
    obligations: list[Obligation],
    ten_van_ban: str,
    so_van_ban: str,
    ngay_hieu_luc: date | datetime,
) -> io.BytesIO:
    """Create a formatted Excel workbook from obligations.

    Returns a BytesIO buffer containing the .xlsx file.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Nghĩa vụ tuân thủ"

    # Row 1: Title (merged)
    ws.merge_cells("A1:I1")
    title_cell = ws["A1"]
    title_cell.value = "Nghĩa vụ pháp luật"
    title_cell.font = Font(bold=True, size=13)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")

    # Row 2: Headers
    for col_idx, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=2, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER

    # Row 3+: Data
    for i, ob in enumerate(obligations):
        row_idx = i + 3
        fill = ALT_FILL if i % 2 == 1 else WHITE_FILL

        # Build nghia vu text: "Điều X. Title\nNội dung"
        noi_dung_plain = _strip_html(ob.noi_dung)
        nghia_vu_text = f"Điều {ob.dieu}. {ob.tieu_de}\n{noi_dung_plain}" if ob.tieu_de else noi_dung_plain

        bat_buoc = "x" if ob.loai == "bat_buoc" else ""

        row_data = [
            ten_van_ban,
            so_van_ban,
            ob.dieu,
            ngay_hieu_luc,
            nghia_vu_text,
            ob.hanh_dong,
            bat_buoc,
            _LOAI_LABEL.get(ob.loai, "Không"),
            ob.chu_the_tuong_tac,
            ob.chu_the_hoat_dong,
        ]

        for col_idx, value in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.fill = fill
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=True)

            if col_idx == 4 and isinstance(value, (date, datetime)):
                cell.number_format = "DD/MM/YYYY"
            if col_idx == 6 and isinstance(value, str) and value:
                cell.value = _parse_bold_markers(value)
            if col_idx in (7, 8):
                cell.alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)

    # Column widths
    for col_idx, width in enumerate(COL_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Row heights
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 30
    for i in range(len(obligations)):
        ws.row_dimensions[i + 3].height = 120

    # Freeze top 2 rows
    ws.freeze_panes = "A3"

    # Save to buffer
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
