"""LLM extraction — 2 prompts per Điều, action streaming."""

import json
import logging
import os
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

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

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
            return response.choices[0].message.content or ""
        except Exception as e:
            if attempt < retry:
                logger.warning(f"LLM call failed (attempt {attempt + 1}): {e}")
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


def _classify(client: OpenAI, article_text: str) -> list[dict]:
    user_prompt = CLASSIFY_USER.format(article_text=article_text)
    response = _call_llm(client, CLASSIFY_SYSTEM, user_prompt)
    return _parse_json_array(response, "obligations")


def extract_obligations_stream(
    chunks: list[Chunk],
) -> Generator[ProgressInfo, None, None]:
    """Yield ProgressInfo per article. Streams action generation tokens."""
    client = OpenAI()
    n = len(chunks)
    timeline: list[TimelineEntry] = []
    t0 = time.time()

    for i, chunk in enumerate(chunks):
        label = f"{chunk.article_id}. {chunk.article_title}"

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
        classified = _classify(client, chunk.text)

        # Step 2: Gen actions only for non-definition articles — STREAMING
        has_obligations = any(
            ob.get("loai") in ("bat_buoc", "quyen") for ob in classified
        )
        actions_map: dict[str, str] = {}
        if has_obligations:
            user_prompt = ACTION_USER.format(article_text=chunk.text)
            final_text = ""
            for partial_text in _call_llm_stream(client, ACTION_SYSTEM, user_prompt):
                final_text = partial_text
                yield ProgressInfo(
                    "streaming", i, n, label, [], list(timeline),
                    streaming_text=partial_text,
                )
            # Parse complete JSON
            actions_list = _parse_json_array(final_text, "actions")
            for a in actions_list:
                actions_map[a.get("dieu", "")] = a.get("hanh_dong", "")

        dur = time.time() - t1

        # Build obligations
        noi_dung_html = _text_to_html(chunk.text)
        obligations = []
        for ob in classified:
            dieu = ob.get("dieu", "")
            obligations.append(Obligation(
                dieu=dieu,
                tieu_de=ob.get("tieu_de", ""),
                noi_dung=noi_dung_html,
                hanh_dong=actions_map.get(dieu, ""),
                loai=ob.get("loai", "bat_buoc"),
            ))

        timeline.append(TimelineEntry(
            timestamp=time.time() - t0, label=label, step="extract",
            duration=dur,
            detail=f"→ {len(obligations)} nghĩa vụ" + (f", {len(actions_map)} hành động" if actions_map else ""),
        ))

        yield ProgressInfo("done", i + 1, n, label, obligations, list(timeline))
