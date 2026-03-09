"""Gradio UI for the Legal Obligation Extractor."""

import tempfile
import time

import gradio as gr
import pandas as pd

from src.chunker import chunk_document
from src.document_reader import extract_metadata, read_document
from src.excel_writer import create_excel
from src.extractor import extract_obligations_stream


def process_document(file):
    """Generator that yields (progress_html, dataframe, excel_path) as extraction runs."""
    if file is None:
        yield "Upload file để bắt đầu.", pd.DataFrame(), None
        return

    t_start = time.time()

    # --- Parsing ---
    yield _status_html(0, 1, "Đọc văn bản...", [], t_start), pd.DataFrame(), None

    try:
        text = read_document(file.name)
    except Exception as e:
        yield f"<b style='color:red'>Lỗi đọc file: {e}</b>", pd.DataFrame(), None
        return

    meta = extract_metadata(text)
    chunks = chunk_document(text)
    total_articles = sum(len(c.articles) for c in chunks)

    header = f"<b>{meta.so_van_ban}</b> — {len(chunks)} chunks, {total_articles} điều"

    # --- LLM extraction (streaming) ---
    all_obligations = []
    df = pd.DataFrame(columns=["Điều", "Loại", "Tiêu đề", "Hành động TCB"])

    for info in extract_obligations_stream(chunks):
        html = _status_html(
            info.articles_done, total_articles,
            info.chunk_label, info.timeline, t_start,
            header=header,
            phase=info.phase,
        )

        if info.phase == "done" and info.new_obligations:
            all_obligations.extend(info.new_obligations)
            df = _build_df(all_obligations)

        yield html, df, None

    # --- Done: generate Excel ---
    if not all_obligations:
        elapsed = time.time() - t_start
        yield (
            header + f"<br><b>Không tìm thấy nghĩa vụ nào.</b> ({elapsed:.0f}s)"
        ), df, None
        return

    excel_buf = create_excel(
        all_obligations, meta.ten_van_ban, meta.so_van_ban, meta.ngay_hieu_luc,
    )
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=f"__{meta.so_van_ban.replace('/', '.')}.xlsx",
        prefix="NghiaVu_",
    )
    tmp.write(excel_buf.getvalue())
    tmp.close()

    elapsed = time.time() - t_start
    final_html = _status_html(
        total_articles, total_articles, "Xong", [],
        t_start, header=header, phase="complete",
        timeline_entries=all_obligations,
    )
    # Rebuild with full timeline from last info
    final_html = _status_html(
        total_articles, total_articles, "Xong", info.timeline,
        t_start, header=header, phase="complete",
    )
    final_html += (
        f"<div style='margin-top:8px;padding:8px;background:#e8f5e9;border-radius:6px'>"
        f"<b style='color:#2e7d32'>Hoàn tất! {len(all_obligations)} nghĩa vụ "
        f"trong {elapsed:.0f}s</b></div>"
    )
    yield final_html, df, tmp.name


def _on_stop(current_html):
    """Called when user clicks Stop — append red stopped message."""
    stop_msg = (
        "<div style='margin-top:8px;padding:8px;background:#ffebee;border-radius:6px'>"
        "<b style='color:#c62828'>Đã dừng trích xuất.</b></div>"
    )
    if current_html and isinstance(current_html, str):
        return current_html + stop_msg
    return stop_msg


def _build_df(obligations):
    return pd.DataFrame([
        {
            "Điều": ob.dieu,
            "Loại": "Bắt buộc" if ob.loai == "bat_buoc" else "Quyền",
            "Tiêu đề": ob.tieu_de,
            "Hành động TCB": ob.hanh_dong,
        }
        for ob in obligations
    ])


def _progress_bar(current: int, total: int, label: str, detail: str = "") -> str:
    pct = int(current / total * 100) if total > 0 else 0
    bar_color = "#4472C4" if pct < 100 else "#2e7d32"
    short = (detail[:50] + "...") if len(detail) > 50 else detail
    return (
        f"<div style='margin:4px 0'>"
        f"<span style='font-size:13px'><b>{label}</b> [{current}/{total}] "
        f"<span style='color:#666'>{short}</span></span>"
        f"<div style='background:#e0e0e0;border-radius:4px;height:7px;margin:2px 0'>"
        f"<div style='background:{bar_color};width:{pct}%;height:100%;border-radius:4px;"
        f"transition:width 0.3s'></div></div></div>"
    )


def _format_duration(secs: float) -> str:
    if secs < 60:
        return f"{secs:.1f}s"
    m, s = divmod(secs, 60)
    return f"{int(m)}m{s:.0f}s"


def _timeline_html(timeline_entries) -> str:
    if not timeline_entries:
        return ""
    rows = []
    for e in timeline_entries:
        icon = "🔍" if e.step == "classify" else "⚡"
        step_label = "Phân loại" if e.step == "classify" else "Sinh hành động"
        ts = _format_duration(e.timestamp)
        dur = _format_duration(e.duration)
        # Shorten chunk label
        short_label = e.chunk_label
        if len(short_label) > 40:
            short_label = short_label[:37] + "..."
        rows.append(
            f"<tr style='font-size:12px;border-bottom:1px solid #eee'>"
            f"<td style='padding:2px 6px;color:#888;white-space:nowrap'>{ts}</td>"
            f"<td style='padding:2px 6px;white-space:nowrap'>{icon} {step_label}</td>"
            f"<td style='padding:2px 6px;color:#555'>{short_label}</td>"
            f"<td style='padding:2px 6px;font-weight:600;white-space:nowrap'>{dur}</td>"
            f"<td style='padding:2px 6px;color:#666'>{e.detail}</td>"
            f"</tr>"
        )
    return (
        "<div style='margin-top:8px;max-height:200px;overflow-y:auto;"
        "border:1px solid #e0e0e0;border-radius:6px'>"
        "<table style='width:100%;border-collapse:collapse'>"
        "<tr style='background:#f5f5f5;font-size:11px;font-weight:600'>"
        "<td style='padding:3px 6px'>Thời gian</td>"
        "<td style='padding:3px 6px'>Bước</td>"
        "<td style='padding:3px 6px'>Chunk</td>"
        "<td style='padding:3px 6px'>Thời lượng</td>"
        "<td style='padding:3px 6px'>Kết quả</td></tr>"
        + "".join(rows)
        + "</table></div>"
    )


def _status_html(articles_done, total_articles, current_label, timeline,
                 t_start, header="", phase="", **_kwargs):
    elapsed = time.time() - t_start
    parts = []

    if header:
        parts.append(f"<div style='margin-bottom:6px'>{header}</div>")

    # Main progress bar - article level
    if phase == "complete":
        detail = f"Hoàn tất — {_format_duration(elapsed)}"
    elif phase == "intent":
        detail = f"Phân loại: {current_label}"
    elif phase == "action":
        detail = f"Sinh hành động: {current_label}"
    else:
        detail = current_label

    parts.append(_progress_bar(articles_done, total_articles, "Tiến trình", detail))

    # Elapsed time
    parts.append(
        f"<div style='font-size:12px;color:#888;margin:2px 0'>"
        f"Thời gian: {_format_duration(elapsed)}</div>"
    )

    # Timeline log
    parts.append(_timeline_html(timeline))

    return "".join(parts)


# --- Build Gradio UI ---
with gr.Blocks(title="Trích xuất Nghĩa vụ Tuân thủ") as app:
    gr.Markdown("## Trích xuất Nghĩa vụ Tuân thủ Pháp luật")

    with gr.Row():
        # Left panel: upload + progress
        with gr.Column(scale=2):
            file_input = gr.File(
                label="Upload văn bản pháp luật (.doc / .docx)",
                file_types=[".doc", ".docx"],
            )
            run_btn = gr.Button("Phân tích", variant="primary")
            stop_btn = gr.Button("Dừng", variant="stop")
            progress_html = gr.HTML(value="Upload file và bấm Phân tích để bắt đầu.")

        # Right panel: results table
        with gr.Column(scale=3):
            results_table = gr.Dataframe(
                headers=["Điều", "Loại", "Tiêu đề", "Hành động TCB"],
                label="Kết quả trích xuất",
                interactive=False,
                wrap=True,
            )
            excel_file = gr.File(label="Tải Excel", visible=True)

    # Wire events
    run_event = run_btn.click(
        fn=process_document,
        inputs=[file_input],
        outputs=[progress_html, results_table, excel_file],
    )
    stop_btn.click(
        fn=_on_stop,
        inputs=[progress_html],
        outputs=[progress_html],
        cancels=[run_event],
    )

if __name__ == "__main__":
    app.launch(theme=gr.themes.Soft())
