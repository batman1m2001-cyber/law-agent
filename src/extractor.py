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
    CHU_THE_HOAT_DONG_SYSTEM, CHU_THE_HOAT_DONG_USER,
    NHOM_NGHIA_VU_SYSTEM, NHOM_NGHIA_VU_USER,
)

load_dotenv()
logger = logging.getLogger(__name__)

MODEL = os.getenv("OPENAI_MODEL", "qwen2.5-72b-instruct")
MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "8192"))

MAX_ARTICLE_CHARS = 30000
LONG_KHOAN_CHARS = 1500  # khoản dài hơn ngưỡng này sẽ được gọi riêng

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
    nhom_nghia_vu: str = ""
    nhom_ly_do: str = ""


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
                max_tokens=MAX_TOKENS,
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
        max_tokens=MAX_TOKENS,
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


def _fix_invalid_escapes(text: str) -> str:
    """Replace invalid JSON escape sequences (e.g. \\T, \\M from Vietnamese text) with \\\\X."""
    return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)


def _fix_control_chars(text: str) -> str:
    """Escape literal control characters (e.g. real newlines) inside JSON string values."""
    result = []
    in_string = False
    escape_next = False
    escape_map = {'\n': '\\n', '\r': '\\r', '\t': '\\t'}
    for c in text:
        if escape_next:
            result.append(c)
            escape_next = False
            continue
        if c == '\\' and in_string:
            result.append(c)
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
            continue
        if in_string and ord(c) < 0x20:
            result.append(escape_map.get(c, f'\\u{ord(c):04x}'))
            continue
        result.append(c)
    return ''.join(result)


def _try_parse(text: str) -> object:
    """Try parsing JSON, applying fixers on failure."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_fix_invalid_escapes(text))
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_fix_control_chars(text))
    except json.JSONDecodeError:
        pass
    return json.loads(_fix_control_chars(_fix_invalid_escapes(text)))


def _parse_json_array(text: str, key: str = "") -> list[dict]:
    text = text.strip()
    try:
        parsed = _try_parse(text)
    except json.JSONDecodeError:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if m:
            parsed = _try_parse(m.group(1))
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


def _resolve_chu_the_hoat_dong(
    client: OpenAI, article_text: str, classified: list[dict]
) -> dict[str, str]:
    """Xác định chu_the_hoat_dong cho các khoản bat_buoc/quyen.
    Trả về dict {dieu -> chu_the_hoat_dong}. Skip nếu không có khoản applicable."""
    applicable = [ob for ob in classified if ob.get("loai") in ("bat_buoc", "quyen")]
    if not applicable:
        return {}
    khoan_list = ", ".join(f'"{ob["dieu"]}" [{ob["loai"]}]' for ob in applicable)
    user_prompt = CHU_THE_HOAT_DONG_USER.format(
        article_text=article_text, khoan_list=khoan_list
    )
    response = _call_llm(client, CHU_THE_HOAT_DONG_SYSTEM, user_prompt)
    parsed = _parse_json_array(response, "obligations")
    return {item["dieu"]: item.get("chu_the_hoat_dong", "") for item in parsed}


def _resolve_nhom_nghia_vu(
    client: OpenAI, article_text: str, classified: list[dict]
) -> dict[str, dict]:
    """Xác định nhom_nghia_vu cho các khoản bat_buoc/quyen.
    Trả về dict {dieu -> {"nhom": ..., "ly_do": ...}}. Skip nếu không có khoản applicable."""
    applicable = [ob for ob in classified if ob.get("loai") in ("bat_buoc", "quyen")]
    if not applicable:
        return {}
    khoan_list = ", ".join(f'"{ob["dieu"]}" [{ob["loai"]}]' for ob in applicable)
    user_prompt = NHOM_NGHIA_VU_USER.format(
        article_text=article_text, khoan_list=khoan_list
    )
    response = _call_llm(client, NHOM_NGHIA_VU_SYSTEM, user_prompt)
    parsed = _parse_json_array(response, "obligations")
    return {item["dieu"]: {"nhom": item.get("nhom", ""), "ly_do": item.get("ly_do", "")} for item in parsed}


def _merge_hoat_dong(classified: list[dict], hoat_dong_map: dict[str, str]) -> list[dict]:
    """Merge kết quả classify với hoat_dong map."""
    merged = []
    for ob in classified:
        loai = ob.get("loai", "bat_buoc")
        chu_the_hoat_dong = "" if loai == "khong_ap_dung" else hoat_dong_map.get(ob.get("dieu", ""), "")
        merged.append({**ob, "chu_the_hoat_dong": chu_the_hoat_dong})
    return merged


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

        # Step 1a: Classify loai + chu_the_tuong_tac
        try:
            classified = _classify(client, chunk.text)
        except Exception as e:
            logger.warning(f"Classify failed for {label}: {e}")
            classified = []

        # Step 1b: Xác định chu_the_hoat_dong và nhom_nghia_vu (skip nếu toàn khong_ap_dung/dinh_nghia)
        nhom_map: dict[str, str] = {}
        if classified:
            try:
                hoat_dong_map = _resolve_chu_the_hoat_dong(client, chunk.text, classified)
            except Exception as e:
                logger.warning(f"Chu the hoat dong failed for {label}: {e}")
                hoat_dong_map = {}
            try:
                nhom_map = _resolve_nhom_nghia_vu(client, chunk.text, classified)
            except Exception as e:
                logger.warning(f"Nhom nghia vu failed for {label}: {e}")
                nhom_map = {}
            classified = _merge_hoat_dong(classified, hoat_dong_map)

        # Step 2: Gen actions only for non-definition articles — STREAMING
        # Khoản ngắn: batch chung 1 lần gọi. Khoản dài (> LONG_KHOAN_CHARS): gọi riêng.
        actions_map: dict[str, str] = {}
        obligation_obs = [ob for ob in classified if ob.get("loai") in ("bat_buoc", "quyen")]
        if obligation_obs:
            loai_map: dict[str, str] = {ob.get("dieu", ""): ob.get("loai", "bat_buoc") for ob in obligation_obs}
            short_keys, long_keys = [], []
            for ob in obligation_obs:
                dieu_key = ob.get("dieu", "")
                khoan_text = _extract_khoan_text(chunk.text, dieu_key)
                if len(khoan_text) > LONG_KHOAN_CHARS:
                    long_keys.append((dieu_key, khoan_text))
                else:
                    short_keys.append((dieu_key, khoan_text))

            # Build list of calls: long khoảns get their own call, short khoảns batched
            calls = [(k, t) for k, t in long_keys]  # one call each
            if short_keys:
                batch_text = "\n\n".join(t for _, t in short_keys)
                batch_keys = [k for k, _ in short_keys]
                calls.append((batch_keys, batch_text))  # one batched call

            for call_keys, call_text in calls:
                if isinstance(call_keys, list):
                    dieu_keys_str = ", ".join(f'"{k}" [{loai_map.get(k, "bat_buoc")}]' for k in call_keys)
                else:
                    dieu_keys_str = f'"{call_keys}" [{loai_map.get(call_keys, "bat_buoc")}]'
                safe_text = call_text.replace("{", "{{").replace("}", "}}")
                user_prompt = ACTION_USER.format(article_text=safe_text, dieu_keys=dieu_keys_str)
                final_text = ""
                try:
                    for partial_text in _call_llm_stream(client, ACTION_SYSTEM, user_prompt):
                        final_text = partial_text
                        yield ProgressInfo(
                            "streaming", i, n, label, [], list(timeline),
                            streaming_text=partial_text,
                        )
                    actions_list = _parse_json_array(final_text, "actions")
                    for a in actions_list:
                        actions_map[a.get("dieu", "")] = a.get("hanh_dong", "")
                except Exception as e:
                    logger.warning(f"Action generation failed for {label} {call_keys}: {e}")

        dur = time.time() - t1

        # Build obligations
        obligations = []
        for ob in classified:
            loai = ob.get("loai", "bat_buoc")

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
                nhom_nghia_vu=nhom_map.get(dieu, {}).get("nhom", "") if isinstance(nhom_map.get(dieu), dict) else nhom_map.get(dieu, ""),
                nhom_ly_do=nhom_map.get(dieu, {}).get("ly_do", "") if isinstance(nhom_map.get(dieu), dict) else "",
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
