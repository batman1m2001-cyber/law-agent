"""
Ước lượng số input/output tokens cho toàn bộ pipeline xử lý một file luật.
Không gọi LLM thực sự — chỉ simulate các prompt và ước lượng token.

Usage:
    python estimate_tokens.py /path/to/file.doc
    python estimate_tokens.py /Users/tramynguyen/Downloads/14_2025_TT-NHNN_632909.doc
"""

import re
import sys
from pathlib import Path

# ── Token counting ─────────────────────────────────────────────────────────────
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
    TOKEN_METHOD = "tiktoken (cl100k_base)"
except ImportError:
    # Fallback: Vietnamese text ~3.5 chars/token (UTF-8 multibyte chars inflate this)
    def count_tokens(text: str) -> int:
        return max(1, len(text) // 3)
    TOKEN_METHOD = "fallback (len/3, no tiktoken installed)"

# ── Project imports ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from src.document_reader import read_document
from src.chunker import chunk_document
from src.prompts import (
    CLASSIFY_SYSTEM, CLASSIFY_USER,
    CHU_THE_HOAT_DONG_SYSTEM, CHU_THE_HOAT_DONG_USER,
    ACTION_SYSTEM, ACTION_USER,
)

# ── Constants (mirror extractor.py) ───────────────────────────────────────────
MAX_ARTICLE_CHARS = 30_000
LONG_KHOAN_CHARS  = 1_500

SKIP_TITLE_KEYWORDS = ["giải thích từ ngữ"]

# ── Output token heuristics ────────────────────────────────────────────────────
# These are conservative estimates based on observed LLM outputs.
# CLASSIFY: ~70 tokens per khoản ({"dieu":"X.Y","loai":"bat_buoc","chu_the_tuong_tac":"..."} + JSON overhead)
CLASSIFY_OUTPUT_PER_KHOAN  = 70
# CHU_THE_HOAT_DONG: ~55 tokens per applicable khoản
CTHO_OUTPUT_PER_KHOAN      = 55
# ACTIONS: ~200 tokens per short khoản (batched), ~350 per long khoản (more detail needed)
ACTION_OUTPUT_SHORT_KHOAN  = 200
ACTION_OUTPUT_LONG_KHOAN   = 350

_KHOAN_RE = re.compile(r'^\d+\.\s', re.MULTILINE)


def _count_khoan(text: str) -> int:
    """Count number of khoản (1. 2. 3. ...) in article text."""
    return max(1, len(_KHOAN_RE.findall(text)))


def _extract_khoan_text(article_text: str, khoan_num: str) -> str:
    matches = list(_KHOAN_RE.finditer(article_text))
    target = None
    for m in matches:
        if m.group(0).startswith(khoan_num + "."):
            target = m
            break
    if target is None:
        return article_text
    start = target.start()
    end = len(article_text)
    for m in matches:
        if m.start() > start:
            end = m.start()
            break
    return article_text[start:end].strip()


def _khoan_texts(article_text: str) -> list[str]:
    """Return list of individual khoản texts (or full text if no khoản markers)."""
    matches = list(_KHOAN_RE.finditer(article_text))
    if not matches:
        return [article_text]
    texts = []
    for idx, m in enumerate(matches):
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(article_text)
        texts.append(article_text[start:end].strip())
    return texts


def _estimate_classify_fraction_applicable(article_text: str) -> float:
    """
    Rough guess: what fraction of khoản are bat_buoc/quyen (not dinh_nghia/khong_ap_dung)?
    Uses a simple heuristic based on keyword presence.
    """
    obligation_keywords = ["phải", "không được", "có nghĩa vụ", "cấm", "bắt buộc",
                           "được phép", "có quyền", "có thể", "được thực hiện",
                           "tối thiểu", "tối đa"]
    text_lower = article_text.lower()
    score = sum(1 for kw in obligation_keywords if kw in text_lower)
    # If many obligation keywords → likely mostly bat_buoc/quyen
    if score >= 4:
        return 0.85
    elif score >= 2:
        return 0.65
    else:
        return 0.35


def estimate_article(chunk) -> dict:
    """Estimate tokens for all LLM calls on a single article chunk."""
    text = chunk.text
    n_khoan = _count_khoan(text)
    khoan_texts_list = _khoan_texts(text)

    # ── Call 1: CLASSIFY ──────────────────────────────────────────────────────
    classify_user = CLASSIFY_USER.format(article_text=text)
    classify_in  = count_tokens(CLASSIFY_SYSTEM) + count_tokens(classify_user)
    classify_out = n_khoan * CLASSIFY_OUTPUT_PER_KHOAN + 20  # +20 JSON wrapper

    # ── Call 2: CHU_THE_HOAT_DONG (conditional) ───────────────────────────────
    applicable_fraction = _estimate_classify_fraction_applicable(text)
    n_applicable = max(1, round(n_khoan * applicable_fraction))

    ctho_in  = 0
    ctho_out = 0
    if n_applicable > 0:
        # khoan_list string: ~25 chars per khoản  e.g. "4.1" [bat_buoc], "4.2" [quyen]
        khoan_list_str = ", ".join(
            f'"X.{i}" [bat_buoc]' for i in range(1, n_applicable + 1)
        )
        ctho_user = CHU_THE_HOAT_DONG_USER.format(
            article_text=text, khoan_list=khoan_list_str
        )
        ctho_in  = count_tokens(CHU_THE_HOAT_DONG_SYSTEM) + count_tokens(ctho_user)
        ctho_out = n_applicable * CTHO_OUTPUT_PER_KHOAN + 20

    # ── Call 3: ACTIONS (streaming, batched) ─────────────────────────────────
    action_in  = 0
    action_out = 0

    short_khoan = [t for t in khoan_texts_list if len(t) <= LONG_KHOAN_CHARS]
    long_khoan  = [t for t in khoan_texts_list if len(t) >  LONG_KHOAN_CHARS]

    # Only for bat_buoc/quyen khoản — apply applicable_fraction as proxy
    # (we don't know exact loai without running CLASSIFY, so use the fraction estimate)
    n_short_applicable = max(0, round(len(short_khoan) * applicable_fraction))
    n_long_applicable  = max(0, round(len(long_khoan)  * applicable_fraction))

    action_sys_tokens = count_tokens(ACTION_SYSTEM)

    if n_short_applicable > 0:
        # All short khoản batched into one call
        short_applicable_texts = short_khoan[:n_short_applicable]
        batch_text   = "\n\n".join(short_applicable_texts)
        batch_keys   = ", ".join(f'"X.{i}" [bat_buoc]' for i in range(1, n_short_applicable + 1))
        safe_text    = batch_text.replace("{", "{{").replace("}", "}}")
        action_user  = ACTION_USER.format(article_text=safe_text, dieu_keys=batch_keys)
        action_in   += action_sys_tokens + count_tokens(action_user)
        action_out  += n_short_applicable * ACTION_OUTPUT_SHORT_KHOAN + 20

    for lt in long_khoan[:n_long_applicable]:
        # Each long khoản gets its own call
        safe_lt     = lt.replace("{", "{{").replace("}", "}}")
        action_user = ACTION_USER.format(article_text=safe_lt, dieu_keys='"X.1" [bat_buoc]')
        action_in  += action_sys_tokens + count_tokens(action_user)
        action_out += ACTION_OUTPUT_LONG_KHOAN + 20

    total_in  = classify_in  + ctho_in  + action_in
    total_out = classify_out + ctho_out + action_out

    return {
        "label":        f"{chunk.article_id}. {chunk.article_title}",
        "n_khoan":      n_khoan,
        "n_applicable": n_applicable,
        "classify_in":  classify_in,
        "classify_out": classify_out,
        "ctho_in":      ctho_in,
        "ctho_out":     ctho_out,
        "action_in":    action_in,
        "action_out":   action_out,
        "total_in":     total_in,
        "total_out":    total_out,
    }


def main(file_path: str):
    path = Path(file_path)
    if not path.exists():
        print(f"[ERROR] File not found: {file_path}")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"  Token Estimation Report")
    print(f"  File   : {path.name}")
    print(f"  Method : {TOKEN_METHOD}")
    print(f"{'='*70}\n")

    # ── Read & chunk ──────────────────────────────────────────────────────────
    print("Reading document...")
    doc_text = read_document(str(path))
    print(f"  → Extracted {len(doc_text):,} characters of plain text")

    print("Chunking into articles...")
    chunks = chunk_document(doc_text)
    print(f"  → Found {len(chunks)} articles\n")

    # ── Pre-compute static prompt sizes ───────────────────────────────────────
    print("Static prompt token sizes:")
    print(f"  CLASSIFY_SYSTEM         : {count_tokens(CLASSIFY_SYSTEM):>6,} tokens")
    print(f"  ACTION_SYSTEM           : {count_tokens(ACTION_SYSTEM):>6,} tokens")
    print(f"  CHU_THE_HOAT_DONG_SYSTEM: {count_tokens(CHU_THE_HOAT_DONG_SYSTEM):>6,} tokens")
    print()

    # ── Per-article estimation ────────────────────────────────────────────────
    results = []
    skipped = []

    for chunk in chunks:
        label = f"{chunk.article_id}. {chunk.article_title}"

        if any(kw in chunk.article_title.lower() for kw in SKIP_TITLE_KEYWORDS):
            skipped.append((label, "giải thích từ ngữ"))
            continue

        if len(chunk.text) > MAX_ARTICLE_CHARS:
            skipped.append((label, f"quá dài ({len(chunk.text):,} ký tự)"))
            continue

        results.append(estimate_article(chunk))

    # ── Summary table ─────────────────────────────────────────────────────────
    print(f"{'Điều':<40} {'Khoản':>6} {'CLASSIFY':>10} {'CTHO':>10} {'ACTIONS':>10} {'TOTAL IN':>10} {'TOTAL OUT':>10}")
    print("-" * 106)

    grand_in  = 0
    grand_out = 0

    for r in results:
        label = r["label"][:39]
        classify = f"{r['classify_in']:,}→{r['classify_out']:,}"
        ctho     = f"{r['ctho_in']:,}→{r['ctho_out']:,}"
        actions  = f"{r['action_in']:,}→{r['action_out']:,}"
        print(
            f"{label:<40} {r['n_khoan']:>6} "
            f"{classify:>10} {ctho:>10} {actions:>10} "
            f"{r['total_in']:>10,} {r['total_out']:>10,}"
        )
        grand_in  += r["total_in"]
        grand_out += r["total_out"]

    print("-" * 106)
    print(f"{'TOTAL (' + str(len(results)) + ' articles processed)':<40} {'':>6} "
          f"{'':>10} {'':>10} {'':>10} "
          f"{grand_in:>10,} {grand_out:>10,}")

    if skipped:
        print(f"\nSkipped {len(skipped)} articles:")
        for label, reason in skipped:
            print(f"  • {label[:60]} — {reason}")

    # ── Cost estimate ─────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  Cost Estimate (approximate)")
    print(f"{'='*70}")
    print(f"  Total input  tokens : {grand_in:>10,}")
    print(f"  Total output tokens : {grand_out:>10,}")
    print(f"  Total tokens        : {grand_in + grand_out:>10,}")
    print()

    # Pricing reference (as of early 2025)
    pricing = {
        "gpt-4o":            (2.50, 10.00),
        "gpt-4o-mini":       (0.15,  0.60),
        "qwen-2.5-72b":      (0.12,  0.39),  # actual pricing
    }
    print("  Estimated cost per model (USD, per 1M tokens):")
    print(f"  {'Model':<25} {'Input':>8} {'Output':>8} {'Est. Cost':>12}")
    print(f"  {'-'*55}")
    for model, (in_price, out_price) in pricing.items():
        cost = (grand_in / 1_000_000) * in_price + (grand_out / 1_000_000) * out_price
        print(f"  {model:<25} ${in_price:>6.2f}  ${out_price:>6.2f}  ${cost:>10.4f}")

    print(f"\n  ⚠  Output tokens are ESTIMATES (heuristic, not from LLM).")
    print(f"  ⚠  Input tokens are accurate if tiktoken is installed.")
    print(f"  ⚠  Retries (up to 2x per failed call) are NOT included.\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python estimate_tokens.py <path_to_doc_file>")
        sys.exit(1)
    main(sys.argv[1])
