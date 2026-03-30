"""Split legal document text into chunks — one chunk per Điều (article)."""

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """A chunk of legal text = one Điều with context metadata."""
    chapter: str  # e.g. "Chương I"
    chapter_title: str
    section: str  # e.g. "Mục 1" or ""
    section_title: str
    article_id: str  # e.g. "Điều 3"
    article_title: str  # e.g. "Giải thích từ ngữ"
    text: str  # Full text of this article


# Patterns for Vietnamese legal document structure
CHAPTER_RE = re.compile(r"^(Chương\s+[IVXLC]+)\s*$", re.MULTILINE)
SECTION_RE = re.compile(r"^(Mục\s+\d+)\.\s*(.+)$", re.MULTILINE)
ARTICLE_RE = re.compile(r"^(Điều\s+\d+)\.\s*(.+)$", re.MULTILINE)


def _find_markers(text: str) -> list[tuple[int, str, str, str]]:
    """Find all structural markers (chapters, sections, articles) with positions.

    Returns list of (position, type, id, title) tuples.
    """
    markers = []

    for m in CHAPTER_RE.finditer(text):
        end = m.end()
        next_line_end = text.find("\n", end + 1)
        if next_line_end == -1:
            next_line_end = len(text)
        title = text[end:next_line_end].strip()
        markers.append((m.start(), "chapter", m.group(1).strip(), title))

    for m in SECTION_RE.finditer(text):
        markers.append((m.start(), "section", m.group(1).strip(), m.group(2).strip()))

    for m in ARTICLE_RE.finditer(text):
        markers.append((m.start(), "article", m.group(1).strip(), m.group(2).strip()))

    markers.sort(key=lambda x: x[0])
    return markers


def chunk_document(text: str) -> list[Chunk]:
    """Split legal document text into chunks — one Chunk per Điều.

    Each chunk contains the full text of a single article with its
    chapter/section context.
    """
    markers = _find_markers(text)
    if not markers:
        return [Chunk(chapter="", chapter_title="", section="", section_title="",
                      article_id="", article_title="", text=text)]

    current_chapter = ""
    current_chapter_title = ""
    current_section = ""
    current_section_title = ""

    chunks: list[Chunk] = []

    for i, (pos, mtype, mid, mtitle) in enumerate(markers):
        if mtype == "chapter":
            current_chapter = mid
            current_chapter_title = mtitle
            current_section = ""
            current_section_title = ""
        elif mtype == "section":
            current_section = mid
            current_section_title = mtitle
        elif mtype == "article":
            # Find end of this article (start of next marker or end of text)
            next_pos = markers[i + 1][0] if i + 1 < len(markers) else len(text)
            article_text = text[pos:next_pos].strip()

            chunks.append(Chunk(
                chapter=current_chapter,
                chapter_title=current_chapter_title,
                section=current_section,
                section_title=current_section_title,
                article_id=mid,
                article_title=mtitle,
                text=article_text,
            ))

    return chunks
