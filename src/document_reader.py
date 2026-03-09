"""Read .doc (OLE binary) and .docx files, extract plain text."""

import re
import struct
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import olefile
from docx import Document


def read_doc_ole(file_path: str | Path) -> str:
    """Extract text from old .doc (OLE/binary) format."""
    ole = olefile.OleFileIO(str(file_path))
    try:
        word_stream = ole.openstream("WordDocument").read()

        # Parse FIB to determine table stream name
        flags = struct.unpack_from("<H", word_stream, 0x000A)[0]
        table_name = "1Table" if (flags & 0x0200) else "0Table"
        table_stream = ole.openstream(table_name).read()

        # Get CLX offset and size from FIB
        fc_clx = struct.unpack_from("<I", word_stream, 0x01A2)[0]
        lcb_clx = struct.unpack_from("<I", word_stream, 0x01A6)[0]
        clx_data = table_stream[fc_clx : fc_clx + lcb_clx]

        # Parse CLX to find piece table
        pos = 0
        text_parts: list[str] = []
        while pos < len(clx_data):
            clx_type = clx_data[pos]
            if clx_type == 0x01:  # grpprl - skip
                cb = struct.unpack_from("<H", clx_data, pos + 1)[0]
                pos += 3 + cb
            elif clx_type == 0x02:  # piece table
                piece_table_size = struct.unpack_from("<I", clx_data, pos + 1)[0]
                piece_table = clx_data[pos + 5 : pos + 5 + piece_table_size]

                n = (piece_table_size - 4) // 12

                for i in range(n):
                    cp_start = struct.unpack_from("<I", piece_table, i * 4)[0]
                    cp_end = struct.unpack_from("<I", piece_table, (i + 1) * 4)[0]

                    pcd_offset = (n + 1) * 4 + i * 8
                    fc_value = struct.unpack_from("<I", piece_table, pcd_offset + 2)[0]

                    is_unicode = not (fc_value & 0x40000000)
                    fc_real = fc_value & 0x3FFFFFFF

                    if is_unicode:
                        byte_start = fc_real
                        byte_len = (cp_end - cp_start) * 2
                        text = word_stream[byte_start : byte_start + byte_len].decode(
                            "utf-16-le", errors="replace"
                        )
                    else:
                        byte_start = fc_real // 2
                        byte_len = cp_end - cp_start
                        text = word_stream[byte_start : byte_start + byte_len].decode(
                            "cp1252", errors="replace"
                        )

                    text_parts.append(text)
                break
            else:
                break

        raw_text = "".join(text_parts)
    finally:
        ole.close()

    # Clean up: replace control chars with newlines, normalize whitespace
    cleaned = []
    for ch in raw_text:
        if ch == "\r" or ch == "\x07":
            cleaned.append("\n")
        elif ch == "\t":
            cleaned.append("\t")
        elif ord(ch) < 32 and ch != "\n":
            cleaned.append("")
        else:
            cleaned.append(ch)
    text = "".join(cleaned)

    # Collapse multiple blank lines
    lines = text.split("\n")
    result_lines: list[str] = []
    prev_blank = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if not prev_blank:
                result_lines.append("")
            prev_blank = True
        else:
            result_lines.append(stripped)
            prev_blank = False

    return "\n".join(result_lines).strip()


def read_docx(file_path: str | Path) -> str:
    """Extract text from .docx format."""
    doc = Document(str(file_path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def read_document(file_path: str | Path) -> str:
    """Read a document file and return plain text.

    Supports .doc (OLE binary) and .docx formats.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".doc":
        return read_doc_ole(path)
    elif suffix == ".docx":
        return read_docx(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Use .doc or .docx")


@dataclass
class DocumentMetadata:
    """Auto-extracted metadata from a legal document."""
    ten_van_ban: str  # Full document name
    so_van_ban: str  # Document number e.g. "83/2025/TT-NHNN"
    ngay_ban_hanh: date | None  # Issue date
    ngay_hieu_luc: date | None  # Effective date (may differ from issue date)


def extract_metadata(text: str) -> DocumentMetadata:
    """Auto-extract metadata (name, number, date) from legal document text."""
    # Extract document number: "Số: XX/YYYY/..."
    so_van_ban = ""
    m = re.search(r"Số:\s*(.+?)[\n\r]", text)
    if m:
        so_van_ban = m.group(1).strip()

    # Extract document type and title
    ten_van_ban = ""
    doc_type_match = re.search(
        r"(THÔNG TƯ|LUẬT|NGHỊ ĐỊNH|QUYẾT ĐỊNH)\s*\n(.+?)(?:\nCăn cứ|\nChương|\nĐiều\s+1)",
        text,
        re.DOTALL,
    )
    if doc_type_match:
        doc_type = doc_type_match.group(1).strip()
        raw_title = doc_type_match.group(2).strip()
        # Normalize title: collapse whitespace, title case
        title = re.sub(r"\s+", " ", raw_title)
        ten_van_ban = f"{doc_type.title()} {title.lower()}"

    # Extract issue date: "ngày X tháng Y năm Z"
    ngay_ban_hanh = None
    m = re.search(r"ngày\s+(\d+)\s+tháng\s+(\d+)\s+năm\s+(\d+)", text[:2000])
    if m:
        try:
            ngay_ban_hanh = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # Extract effective date: "có hiệu lực từ ngày DD/MM/YYYY" or "hiệu lực từ ngày X tháng Y năm Z"
    ngay_hieu_luc = None
    m = re.search(r"hiệu lực.*?(\d{1,2})[/.](\d{1,2})[/.](\d{4})", text, re.IGNORECASE)
    if m:
        try:
            ngay_hieu_luc = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    if not ngay_hieu_luc:
        m = re.search(
            r"hiệu lực.*?ngày\s+(\d+)\s+tháng\s+(\d+)\s+năm\s+(\d+)",
            text,
            re.IGNORECASE,
        )
        if m:
            try:
                ngay_hieu_luc = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass

    # Fallback: use issue date if no effective date found
    if not ngay_hieu_luc:
        ngay_hieu_luc = ngay_ban_hanh

    return DocumentMetadata(
        ten_van_ban=ten_van_ban,
        so_van_ban=so_van_ban,
        ngay_ban_hanh=ngay_ban_hanh,
        ngay_hieu_luc=ngay_hieu_luc,
    )
