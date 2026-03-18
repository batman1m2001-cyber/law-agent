"""Hush ops for legal obligation extraction."""

import json
import re
import struct
from pathlib import Path

from hush.core import op

# =============================================================================
# Constants
# =============================================================================

MAX_ARTICLE_CHARS = 30000
SKIP_TITLE_KEYWORDS = ["giải thích từ ngữ"]

CHAPTER_RE = re.compile(r"^(Chương\s+[IVXLC]+)\s*$", re.MULTILINE)
SECTION_RE = re.compile(r"^(Mục\s+\d+)\.\s*(.+)$", re.MULTILINE)
ARTICLE_RE = re.compile(r"^(Điều\s+\d+)\.\s*(.+)$", re.MULTILINE)

# =============================================================================
# Op: Read document
# =============================================================================


@op(executor="thread")
def read_doc(file_path: str):
    """Read .doc/.docx file, return plain text + metadata."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".doc":
        text = _read_doc_ole(path)
    elif suffix == ".docx":
        text = _read_docx(path)
    else:
        raise ValueError(f"Unsupported format: {suffix}")

    return {"text": text, "metadata": _extract_metadata(text)}


# =============================================================================
# Op: Chunk and save (generator)
# =============================================================================


@op
def chunk_and_save(text: str, metadata: dict, output_path: str, max_articles: int = -1):
    """Chunk document, save new articles to JSON, yield articles needing work.

    Statuses:
      pending / error_classify  → yield with skip_classify=False (needs full pipeline)
      classified / error_actions → yield with skip_classify=True (has classified_json, skip LLM)
      done / skipped            → skip entirely
    """
    articles = _chunk_text(text)

    json_path = Path(output_path)
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
    else:
        data = {"doc_id": metadata.get("so_van_ban", ""), "metadata": metadata, "articles": {}}

    # Append new chunks only
    for art in articles:
        key = art["article_id"]
        if key not in data["articles"]:
            data["articles"][key] = {
                "title": art["title"],
                "chapter": art["chapter"],
                "chapter_title": art["chapter_title"],
                "text": art["text"],
                "status": "pending",
            }

    _save_json(json_path, data)

    # Yield based on status
    yielded = 0
    for key, art in data["articles"].items():
        if max_articles >= 0 and yielded >= max_articles:
            break
        if art["status"] in ("done", "skipped"):
            continue

        if any(kw in art.get("title", "").lower() for kw in SKIP_TITLE_KEYWORDS):
            art["status"] = "skipped"
            _save_json(json_path, data)
            continue

        if len(art.get("text", "")) > MAX_ARTICLE_CHARS:
            art["status"] = "skipped"
            art["error"] = f"Too long ({len(art['text']):,} chars)"
            _save_json(json_path, data)
            continue

        # Has classified_json? Skip classify LLM call
        classified_json = art.get("classified_json", "")
        skip_classify = bool(classified_json)

        yielded += 1
        yield {
            "article_id": key,
            "title": art["title"],
            "text": art["text"],
            "output_path": output_path,
            "skip_classify": skip_classify,
            "classified_json": classified_json,
        }


# =============================================================================
# Op: Parse classify result, prepare for action generation
# =============================================================================


@op
def parse_and_prepare(
    article_id: str, title: str, text: str, output_path: str,
    classify_content: str = "", cached_content: str = "",
):
    """Parse classify JSON, build dieu_keys for action generation."""
    content = classify_content or cached_content
    obligations = _parse_json_array(content, "obligations")
    has_obligations = any(ob.get("loai") in ("bat_buoc", "quyen") for ob in obligations)

    dieu_keys = ""
    if has_obligations:
        keys = [ob.get("dieu", "") for ob in obligations if ob.get("loai") in ("bat_buoc", "quyen")]
        dieu_keys = ", ".join(f'"{k}"' for k in keys)

    safe_text = text.replace("{", "{{").replace("}", "}}")

    return {
        "article_id": article_id,
        "title": title,
        "text": text,
        "output_path": output_path,
        "classified_json": content,
        "has_obligations": has_obligations,
        "dieu_keys": dieu_keys,
        "safe_text": safe_text,
    }


# =============================================================================
# Op: Save classify result to JSON (status → "classified")
# =============================================================================


@op
def save_classify(article_id: str, output_path: str, classified_json: str):
    """Save classify result to JSON, set status='classified'."""
    json_path = Path(output_path)
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["articles"][article_id]["status"] = "classified"
        data["articles"][article_id]["classified_json"] = classified_json
        _save_json(json_path, data)
    except Exception as e:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["articles"][article_id]["status"] = "error_classify"
        data["articles"][article_id]["error"] = str(e)
        _save_json(json_path, data)
        raise
    return {"article_id": article_id, "classified_json": classified_json}


# =============================================================================
# Op: Save final result to JSON (status → "done")
# =============================================================================


@op
def save_actions(
    article_id: str, output_path: str, classified_json: str, actions_content: str,
):
    """Parse classify + actions, build obligations, save to JSON as 'done'."""
    json_path = Path(output_path)

    try:
        classified = _parse_json_array(classified_json, "obligations")

        actions_map = {}
        if actions_content:
            for a in _parse_json_array(actions_content, "actions"):
                dieu_key = a.get("dieu", "")
                hanh_dong = a.get("hanh_dong", "")
                if dieu_key in actions_map:
                    actions_map[dieu_key] += "\n" + hanh_dong
                else:
                    actions_map[dieu_key] = hanh_dong

        obligations = []
        seen_dinh_nghia = False
        for ob in classified:
            loai = ob.get("loai", "bat_buoc")
            if loai == "dinh_nghia":
                if seen_dinh_nghia:
                    continue
                seen_dinh_nghia = True

            dieu = ob.get("dieu", "")
            obligations.append({
                "dieu": dieu,
                "loai": loai,
                "hanh_dong": actions_map.get(dieu, ""),
                "chu_the_tuong_tac": ob.get("chu_the_tuong_tac", ""),
                "chu_the_hoat_dong": ob.get("chu_the_hoat_dong", ""),
            })

        obligations = [ob for ob in obligations if ob["dieu"].count(".") <= 1]
        child_bases = {ob["dieu"].split(".")[0] for ob in obligations if "." in ob["dieu"]}
        obligations = [ob for ob in obligations if "." in ob["dieu"] or ob["dieu"] not in child_bases]

        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["articles"][article_id]["status"] = "done"
        data["articles"][article_id]["obligations"] = obligations
        data["articles"][article_id].pop("error", None)
        _save_json(json_path, data)

    except Exception as e:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["articles"][article_id]["status"] = "error_actions"
        data["articles"][article_id]["error"] = str(e)
        _save_json(json_path, data)
        raise

    return {"article_id": article_id, "count": len(obligations)}


# =============================================================================
# Helper
# =============================================================================


def _save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# =============================================================================
# Internal helpers
# =============================================================================


def _read_doc_ole(file_path: Path) -> str:
    import olefile

    ole = olefile.OleFileIO(str(file_path))
    try:
        word_stream = ole.openstream("WordDocument").read()
        flags = struct.unpack_from("<H", word_stream, 0x000A)[0]
        table_name = "1Table" if (flags & 0x0200) else "0Table"
        table_stream = ole.openstream(table_name).read()
        fc_clx = struct.unpack_from("<I", word_stream, 0x01A2)[0]
        lcb_clx = struct.unpack_from("<I", word_stream, 0x01A6)[0]
        clx_data = table_stream[fc_clx : fc_clx + lcb_clx]

        pos = 0
        text_parts = []
        while pos < len(clx_data):
            clx_type = clx_data[pos]
            if clx_type == 0x01:
                cb = struct.unpack_from("<H", clx_data, pos + 1)[0]
                pos += 3 + cb
            elif clx_type == 0x02:
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
                        t = word_stream[byte_start : byte_start + byte_len].decode(
                            "utf-16-le", errors="replace"
                        )
                    else:
                        byte_start = fc_real // 2
                        byte_len = cp_end - cp_start
                        t = word_stream[byte_start : byte_start + byte_len].decode(
                            "cp1252", errors="replace"
                        )
                    text_parts.append(t)
                break
            else:
                break
        raw_text = "".join(text_parts)
    finally:
        ole.close()

    cleaned = []
    for ch in raw_text:
        if ch in ("\r", "\x07"):
            cleaned.append("\n")
        elif ch == "\t":
            cleaned.append("\t")
        elif ord(ch) < 32 and ch != "\n":
            cleaned.append("")
        else:
            cleaned.append(ch)
    text = "".join(cleaned)

    lines = text.split("\n")
    result_lines = []
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


def _read_docx(file_path: Path) -> str:
    from docx import Document

    doc = Document(str(file_path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_metadata(text: str) -> dict:
    so_van_ban = ""
    m = re.search(r"Số:\s*(.+?)[\n\r]", text)
    if m:
        so_van_ban = m.group(1).strip()

    ten_van_ban = ""
    m = re.search(
        r"(THÔNG TƯ|LUẬT|NGHỊ ĐỊNH|QUYẾT ĐỊNH)\s*\n(.+?)(?:\nCăn cứ|\nChương|\nĐiều\s+1)",
        text, re.DOTALL,
    )
    if m:
        doc_type = m.group(1).strip().title()
        raw_title = re.sub(r"\s+", " ", m.group(2).strip()).lower()
        ten_van_ban = f"{doc_type} {raw_title}"

    ngay_ban_hanh = ""
    m = re.search(r"ngày\s+(\d+)\s+tháng\s+(\d+)\s+năm\s+(\d+)", text[:2000])
    if m:
        ngay_ban_hanh = f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

    ngay_hieu_luc = ""
    m = re.search(r"hiệu lực.*?(\d{1,2})[/.](\d{1,2})[/.](\d{4})", text, re.IGNORECASE)
    if m:
        ngay_hieu_luc = f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    if not ngay_hieu_luc:
        m = re.search(r"hiệu lực.*?ngày\s+(\d+)\s+tháng\s+(\d+)\s+năm\s+(\d+)", text, re.IGNORECASE)
        if m:
            ngay_hieu_luc = f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    if not ngay_hieu_luc:
        ngay_hieu_luc = ngay_ban_hanh

    return {
        "ten_van_ban": ten_van_ban,
        "so_van_ban": so_van_ban,
        "ngay_ban_hanh": ngay_ban_hanh,
        "ngay_hieu_luc": ngay_hieu_luc,
    }


def _chunk_text(text: str) -> list[dict]:
    markers = []
    for m in CHAPTER_RE.finditer(text):
        end = m.end()
        next_line_end = text.find("\n", end + 1)
        if next_line_end == -1:
            next_line_end = len(text)
        markers.append((m.start(), "chapter", m.group(1).strip(), text[end:next_line_end].strip()))
    for m in SECTION_RE.finditer(text):
        markers.append((m.start(), "section", m.group(1).strip(), m.group(2).strip()))
    for m in ARTICLE_RE.finditer(text):
        markers.append((m.start(), "article", m.group(1).strip(), m.group(2).strip()))
    markers.sort(key=lambda x: x[0])

    if not markers:
        return [{"article_id": "Điều 0", "title": "", "chapter": "", "chapter_title": "", "text": text}]

    current_chapter = ""
    current_chapter_title = ""
    articles = []
    for i, (pos, mtype, mid, mtitle) in enumerate(markers):
        if mtype == "chapter":
            current_chapter = mid
            current_chapter_title = mtitle
        elif mtype == "article":
            next_pos = markers[i + 1][0] if i + 1 < len(markers) else len(text)
            articles.append({
                "article_id": mid,
                "title": mtitle,
                "chapter": current_chapter,
                "chapter_title": current_chapter_title,
                "text": text[pos:next_pos].strip(),
            })
    return articles


def _parse_json_array(text: str, key: str = "") -> list[dict]:
    text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if m:
            parsed = json.loads(m.group(1))
        else:
            raise
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        if key and key in parsed and isinstance(parsed[key], list):
            return parsed[key]
        for v in parsed.values():
            if isinstance(v, list):
                return v
        if "dieu" in parsed:
            return [parsed]
    return []
