"""LLM extraction — 2 prompts per Điều, action streaming."""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Generator

from dotenv import load_dotenv
from openai import OpenAI

from .chunker import Chunk
from .document_reader import _text_to_html
from .prompts import (
    ACTION_SYSTEM, ACTION_USER,
    CLASSIFY_SYSTEM, CLASSIFY_USER,
)

load_dotenv()
logger = logging.getLogger(__name__)

_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()

if _PROVIDER == "openrouter":
    MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct")
    _CLIENT = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )
else:
    MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
    _CLIENT = OpenAI()

logger.info(f"LLM provider: {_PROVIDER}, model: {MODEL}")

MAX_ARTICLE_CHARS = 30000

STREAM_YIELD_EVERY = 15  # yield every N chars to avoid overwhelming UI


@dataclass
class Obligation:
    """A single extracted legal obligation."""
    dieu: str
    tieu_de: str
    noi_dung: str  # HTML formatted from original doc
    hanh_dong: str
    loai: str
    chu_the_tuong_tac: str = ""
    chu_the_hoat_dong: str = ""


@dataclass
class TimelineEntry:
    timestamp: float
    label: str
    step: str
    duration: float
    detail: str


@dataclass
class ProgressInfo:
    phase: str  # "extracting" | "streaming" | "done" | "skip"
    articles_done: int
    total_articles: int
    article_label: str
    new_obligations: list[Obligation]
    timeline: list[TimelineEntry] = field(default_factory=list)
    streaming_text: str = ""


def _call_llm(client: OpenAI, system: str, user: str, retry: int = 2) -> str:
    for attempt in range(retry + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            content = response.choices[0].message.content or ""
            if not content.strip():
                raise ValueError("LLM returned empty content (possible rate limit)")
            return content
        except Exception as e:
            if attempt < retry:
                wait = 2 ** attempt  # 1s, 2s, 4s ...
                logger.warning(f"LLM call failed (attempt {attempt + 1}): {e} — retrying in {wait}s")
                time.sleep(wait)
                continue
            raise


def _call_llm_stream(client: OpenAI, system: str, user: str) -> Generator[str, None, None]:
    """Stream LLM response, yielding accumulated text progressively."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        stream=True,
    )
    accumulated = ""
    chars_since_yield = 0
    for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            accumulated += delta
            chars_since_yield += len(delta)
            if chars_since_yield >= STREAM_YIELD_EVERY:
                chars_since_yield = 0
                yield accumulated
    # Final yield with complete text
    yield accumulated


def _parse_json_array(text: str, key: str = "") -> list[dict]:
    text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        import re
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


_KHOAN_RE = re.compile(r'^(\d+)\.\s', re.MULTILINE)


def _extract_khoan_text(article_text: str, dieu: str) -> str:
    """Extract the khoản text for a dieu code like '4.2' (khoản 2).
    Falls back to full article text if khoản not found or dieu has no sub-number.
    """
    parts = dieu.split(".")
    if len(parts) < 2:
        return article_text
    khoan_num = parts[1]
    matches = list(_KHOAN_RE.finditer(article_text))
    target = None
    for m in matches:
        if m.group(1) == khoan_num:
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


def _classify(client: OpenAI, article_text: str) -> list[dict]:
    user_prompt = CLASSIFY_USER.format(article_text=article_text)
    response = _call_llm(client, CLASSIFY_SYSTEM, user_prompt)
    return _parse_json_array(response, "obligations")


def extract_obligations_stream(
    chunks: list[Chunk],
) -> Generator[ProgressInfo, None, None]:
    """Yield ProgressInfo per article. Streams action generation tokens."""
    client = _CLIENT
    n = len(chunks)
    timeline: list[TimelineEntry] = []
    t0 = time.time()

    for i, chunk in enumerate(chunks):
        label = f"{chunk.article_id}. {chunk.article_title}"

        SKIP_TITLE_KEYWORDS = ["giải thích từ ngữ"]
        if any(kw in chunk.article_title.lower() for kw in SKIP_TITLE_KEYWORDS):
            timeline.append(TimelineEntry(
                timestamp=time.time() - t0, label=label, step="skip",
                duration=0, detail="Bỏ qua: điều giải thích từ ngữ",
            ))
            yield ProgressInfo("skip", i + 1, n, label, [], list(timeline))
            continue

        if len(chunk.text) > MAX_ARTICLE_CHARS:
            timeline.append(TimelineEntry(
                timestamp=time.time() - t0, label=label, step="skip",
                duration=0, detail=f"Quá dài ({len(chunk.text):,} ký tự)",
            ))
            yield ProgressInfo("skip", i + 1, n, label, [], list(timeline))
            continue

        yield ProgressInfo("extracting", i, n, label, [], list(timeline))

        t1 = time.time()

        # Step 1: Classify (fast, no streaming needed)
        try:
            classified = _classify(client, chunk.text)
        except Exception as e:
            logger.warning(f"Classify failed for {label}: {e}")
            classified = []

        # Step 2: Gen actions only for non-definition articles — STREAMING
        has_obligations = any(
            ob.get("loai") in ("bat_buoc", "quyen") for ob in classified
        )
        actions_map: dict[str, str] = {}
        if has_obligations:
            obligation_dieu_keys = [ob.get("dieu", "") for ob in classified if ob.get("loai") in ("bat_buoc", "quyen")]
            dieu_keys_str = ", ".join(f'"{k}"' for k in obligation_dieu_keys)
            # Escape braces in article text to avoid .format() KeyError
            safe_text = chunk.text.replace("{", "{{").replace("}", "}}")
            user_prompt = ACTION_USER.format(article_text=safe_text, dieu_keys=dieu_keys_str)
            final_text = ""
            try:
                for partial_text in _call_llm_stream(client, ACTION_SYSTEM, user_prompt):
                    final_text = partial_text
                    yield ProgressInfo(
                        "streaming", i, n, label, [], list(timeline),
                        streaming_text=partial_text,
                    )
                # Parse complete JSON
                actions_list = _parse_json_array(final_text, "actions")
                for a in actions_list:
                    dieu_key = a.get("dieu", "")
                    hanh_dong = a.get("hanh_dong", "")
                    if dieu_key in actions_map:
                        actions_map[dieu_key] += "\n" + hanh_dong
                    else:
                        actions_map[dieu_key] = hanh_dong
            except Exception as e:
                logger.warning(f"Action generation failed for {label}: {e}")

        dur = time.time() - t1

        # Build obligations
        obligations = []
        seen_dinh_nghia = False
        for ob in classified:
            loai = ob.get("loai", "bat_buoc")

            # Deduplicate: only 1 dinh_nghia entry per article
            if loai == "dinh_nghia":
                if seen_dinh_nghia:
                    continue
                seen_dinh_nghia = True

            dieu = ob.get("dieu", "")
            # Extract only the relevant khoản text for this obligation
            khoan_text = _extract_khoan_text(chunk.text, dieu)
            noi_dung_html = _text_to_html(khoan_text)
            # Use article title from the law document, not LLM-generated tiêu đề
            tieu_de = chunk.article_title
            obligations.append(Obligation(
                dieu=dieu,
                tieu_de=tieu_de,
                noi_dung=noi_dung_html,
                hanh_dong=actions_map.get(dieu, ""),
                loai=loai,
                chu_the_tuong_tac=ob.get("chu_the_tuong_tac", ""),
                chu_the_hoat_dong=ob.get("chu_the_hoat_dong", ""),
            ))

        # Drop invalid điểm-level entries (e.g. dieu="6.4.a") — only article and khoản levels allowed
        obligations = [ob for ob in obligations if ob.dieu.count(".") <= 1]

        # Drop whole-article entries (e.g. dieu="24") when sub-khoản entries exist (e.g. "24.1", "24.2")
        child_bases = {ob.dieu.split(".")[0] for ob in obligations if "." in ob.dieu}
        obligations = [ob for ob in obligations if "." in ob.dieu or ob.dieu not in child_bases]

        timeline.append(TimelineEntry(
            timestamp=time.time() - t0, label=label, step="extract",
            duration=dur,
            detail=f"→ {len(obligations)} nghĩa vụ" + (f", {len(actions_map)} hành động" if actions_map else ""),
        ))

        yield ProgressInfo("done", i + 1, n, label, obligations, list(timeline))
