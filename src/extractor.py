"""LLM extraction pipeline: Node 1 (classify) → Node 2 (generate actions)."""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Generator

from dotenv import load_dotenv
from openai import OpenAI

from .chunker import Chunk
from .prompts import NODE1_SYSTEM, NODE1_USER, NODE2_SYSTEM, NODE2_USER

load_dotenv()
logger = logging.getLogger(__name__)

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


@dataclass
class Obligation:
    """A single extracted legal obligation."""
    dieu: str
    tieu_de: str
    noi_dung: str
    hanh_dong: str
    loai: str  # "bat_buoc" or "quyen"


@dataclass
class TimelineEntry:
    """A single entry in the processing timeline."""
    timestamp: float  # seconds since start
    chunk_label: str
    step: str  # "classify" | "actions"
    duration: float  # seconds
    detail: str  # e.g. "→ 8 nghĩa vụ"


@dataclass
class ProgressInfo:
    """Progress update yielded during extraction."""
    phase: str  # "intent" | "action" | "done"
    articles_done: int  # cumulative articles processed
    total_articles: int
    chunk_label: str
    new_obligations: list[Obligation]
    timeline: list[TimelineEntry] = field(default_factory=list)


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


def _parse_json_array(text: str) -> list[dict]:
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
        for v in parsed.values():
            if isinstance(v, list):
                return v
        if "dieu" in parsed:
            return [parsed]
    return []


def _node1_classify(client: OpenAI, chunk: Chunk) -> list[dict]:
    user_prompt = NODE1_USER.format(chunk_text=chunk.text)
    response = _call_llm(client, NODE1_SYSTEM, user_prompt)
    items = _parse_json_array(response)
    return [item for item in items if item.get("loai") != "bo_qua"]


def _node2_actions(client: OpenAI, obligations: list[dict]) -> list[dict]:
    if not obligations:
        return []
    input_data = [
        {"dieu": ob.get("dieu", ""), "noi_dung": ob.get("noi_dung", "")}
        for ob in obligations
    ]
    user_prompt = NODE2_USER.format(
        obligations_json=json.dumps(input_data, ensure_ascii=False, indent=2)
    )
    response = _call_llm(client, NODE2_SYSTEM, user_prompt)
    return _parse_json_array(response)


def extract_obligations_stream(
    chunks: list[Chunk],
) -> Generator[ProgressInfo, None, None]:
    """Yield ProgressInfo after each step so UI can update in real time."""
    client = OpenAI()
    total_articles = sum(len(c.articles) for c in chunks)
    articles_done = 0
    timeline: list[TimelineEntry] = []
    t0 = time.time()

    for i, chunk in enumerate(chunks):
        chunk_label = chunk.chapter
        if chunk.section:
            chunk_label += f" > {chunk.section}"
        chunk_label += f" ({', '.join(chunk.articles)})"
        chunk_article_count = len(chunk.articles)

        # Node 1 - about to start
        yield ProgressInfo("intent", articles_done, total_articles, chunk_label, [],
                           list(timeline))

        t1 = time.time()
        classified = _node1_classify(client, chunk)
        dur1 = time.time() - t1

        n_found = len(classified)
        timeline.append(TimelineEntry(
            timestamp=time.time() - t0,
            chunk_label=chunk_label,
            step="classify",
            duration=dur1,
            detail=f"→ {n_found} nghĩa vụ" if n_found else "→ bỏ qua",
        ))

        if not classified:
            articles_done += chunk_article_count
            yield ProgressInfo("done", articles_done, total_articles, chunk_label, [],
                               list(timeline))
            continue

        # Node 2 - about to start
        yield ProgressInfo("action", articles_done, total_articles, chunk_label, [],
                           list(timeline))

        t2 = time.time()
        batch_size = 15
        actions_map: dict[str, str] = {}
        for batch_start in range(0, len(classified), batch_size):
            batch = classified[batch_start: batch_start + batch_size]
            actions = _node2_actions(client, batch)
            for action in actions:
                actions_map[action.get("dieu", "")] = action.get("hanh_dong", "")
        dur2 = time.time() - t2

        timeline.append(TimelineEntry(
            timestamp=time.time() - t0,
            chunk_label=chunk_label,
            step="actions",
            duration=dur2,
            detail=f"→ {len(actions_map)} hành động",
        ))

        # Build obligations for this chunk
        chunk_obs = []
        for ob in classified:
            dieu = ob.get("dieu", "")
            chunk_obs.append(Obligation(
                dieu=dieu,
                tieu_de=ob.get("tieu_de", ""),
                noi_dung=ob.get("noi_dung", ""),
                hanh_dong=actions_map.get(dieu, ""),
                loai=ob.get("loai", "bat_buoc"),
            ))

        articles_done += chunk_article_count
        yield ProgressInfo("done", articles_done, total_articles, chunk_label, chunk_obs,
                           list(timeline))
