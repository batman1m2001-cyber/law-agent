"""Split legal document text into chunks by Chương/Mục/Điều structure."""

import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """A chunk of legal text with metadata."""
    chapter: str  # e.g. "Chương I"
    chapter_title: str  # e.g. "QUY ĐỊNH CHUNG"
    section: str  # e.g. "Mục 1" or ""
    section_title: str  # e.g. "QUY ĐỊNH CHUNG VỀ HOẠT ĐỘNG QUẢN LÝ RỦI RO" or ""
    articles: list[str] = field(default_factory=list)  # e.g. ["Điều 4", "Điều 5"]
    text: str = ""  # The actual text content


# Patterns for Vietnamese legal document structure
CHAPTER_RE = re.compile(r"^(Chương\s+[IVXLC]+)\s*$", re.MULTILINE)
SECTION_RE = re.compile(r"^(Mục\s+\d+)\.\s*(.+)$", re.MULTILINE)
ARTICLE_RE = re.compile(r"^(Điều\s+\d+)\.\s*(.+)$", re.MULTILINE)

# Approximate chars per token for Vietnamese text
CHARS_PER_TOKEN = 3
MAX_CHUNK_TOKENS = 8000
MAX_CHUNK_CHARS = MAX_CHUNK_TOKENS * CHARS_PER_TOKEN


def _find_markers(text: str) -> list[tuple[int, str, str, str]]:
    """Find all structural markers (chapters, sections, articles) with positions.

    Returns list of (position, type, id, title) tuples.
    type: 'chapter', 'section', 'article'
    """
    markers = []

    for m in CHAPTER_RE.finditer(text):
        # Try to get chapter title from next line
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
    """Split legal document text into chunks by Chương/Mục structure.

    Each chunk contains articles under the same Chương/Mục.
    If a chunk is too large, it will be split into smaller chunks by article groups.
    """
    markers = _find_markers(text)
    if not markers:
        return [Chunk(chapter="", chapter_title="", section="", section_title="",
                      articles=[], text=text)]

    # Group articles by their chapter/section context
    current_chapter = ""
    current_chapter_title = ""
    current_section = ""
    current_section_title = ""

    # Build article ranges
    article_ranges: list[dict] = []

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

            article_ranges.append({
                "chapter": current_chapter,
                "chapter_title": current_chapter_title,
                "section": current_section,
                "section_title": current_section_title,
                "article_id": mid,
                "article_title": mtitle,
                "text": article_text,
                "pos": pos,
            })

    # Group articles into chunks by chapter+section
    chunks: list[Chunk] = []
    current_group: list[dict] = []
    current_key = None

    for art in article_ranges:
        key = (art["chapter"], art["section"])
        if key != current_key:
            if current_group:
                chunks.extend(_build_chunks_from_group(current_group))
            current_group = [art]
            current_key = key
        else:
            current_group.append(art)

    if current_group:
        chunks.extend(_build_chunks_from_group(current_group))

    return chunks


def _build_chunks_from_group(articles: list[dict]) -> list[Chunk]:
    """Build one or more chunks from a group of articles under the same chapter/section.

    Splits into smaller chunks if text exceeds MAX_CHUNK_CHARS.
    """
    if not articles:
        return []

    ref = articles[0]
    combined_text = "\n\n".join(a["text"] for a in articles)

    if len(combined_text) <= MAX_CHUNK_CHARS:
        return [Chunk(
            chapter=ref["chapter"],
            chapter_title=ref["chapter_title"],
            section=ref["section"],
            section_title=ref["section_title"],
            articles=[a["article_id"] for a in articles],
            text=combined_text,
        )]

    # Split into smaller chunks
    chunks = []
    current_articles: list[dict] = []
    current_len = 0

    for art in articles:
        art_len = len(art["text"])
        if current_len + art_len > MAX_CHUNK_CHARS and current_articles:
            chunks.append(Chunk(
                chapter=ref["chapter"],
                chapter_title=ref["chapter_title"],
                section=ref["section"],
                section_title=ref["section_title"],
                articles=[a["article_id"] for a in current_articles],
                text="\n\n".join(a["text"] for a in current_articles),
            ))
            current_articles = []
            current_len = 0

        current_articles.append(art)
        current_len += art_len

    if current_articles:
        chunks.append(Chunk(
            chapter=ref["chapter"],
            chapter_title=ref["chapter_title"],
            section=ref["section"],
            section_title=ref["section_title"],
            articles=[a["article_id"] for a in current_articles],
            text="\n\n".join(a["text"] for a in current_articles),
        ))

    return chunks
